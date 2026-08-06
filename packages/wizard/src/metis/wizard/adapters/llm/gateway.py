"""The real interviewer, over the PlatformAI gateway.

The gateway is OpenAI-compatible, so the client is `OpenAI` with a `base_url` — and it serves
both chat and embeddings on one endpoint and key, which is why the matcher is not a second
integration.

Every call asks for structured output and retries twice on a validation failure, feeding the
error back each time. Three attempts total, silent unless all three fail: a first-attempt
schema miss is common and recoverable, and asking the user about it makes them the retry loop.

Recovery is silent in a second sense: a retried turn's `message` — the intro the user reads —
tends to narrate the correction itself ("I've corrected the criteria format"), which is
implementation detail no user should see. So `_step` drops the intro whenever a retry was
needed and lets the driver fall back to its neutral per-step default. The patches, which are
the actual output, are kept regardless. The model cannot leak its own recovery because that
text never leaves the gateway — a code guarantee, not a prompt instruction.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from metis.wizard.adapters.llm import tracing
from metis.wizard.application import prompts
from metis.wizard.application.interviewer import (
    ClarifyPhase,
    InterviewerOutputError,
    InterviewerUnavailable,
)
from metis.wizard.contracts.output import ClarifyResult, StepResult
from metis.wizard.contracts.session_state import Turn
from metis.wizard.domain.applier import PatchValueError, validate_model_patches
from metis.wizard.domain.profile import ProductProfile

BASE_URL_VAR = "PLATFORM_API_BASE_URL"
API_KEY_VAR = "PLATFORM_API_KEY"
MODEL_VAR = "PLATFORM_INTERVIEW_MODEL"

DEFAULT_MODEL = "gemini-3.5-flash-lite"
GATEWAY_SUFFIX = "/platform/models/v1"

ATTEMPTS = 3

T = TypeVar("T", bound=BaseModel)


class CredentialsMissing(InterviewerUnavailable):
    """The gateway is not configured. Raised before any call is attempted."""


class ModelOutputError(InterviewerOutputError):
    """Three attempts, all of them malformed."""


def check_credentials() -> None:
    """Fail before any model call when the environment is not set up.

    Named variables rather than a generic "not configured": the fix is to export something,
    so the message should say what.
    """
    missing = [v for v in (BASE_URL_VAR, API_KEY_VAR) if not os.environ.get(v)]
    if missing:
        raise CredentialsMissing(
            f"The wizard needs {' and '.join(missing)} in the environment to reach the "
            f"model gateway. Set {'them' if len(missing) > 1 else 'it'} and try again."
        )


@dataclass
class GatewayInterviewer:
    """Structured-output calls against the gateway."""

    model: str = field(default_factory=lambda: os.environ.get(MODEL_VAR, DEFAULT_MODEL))
    _client: Any = None
    session_id: str | None = None
    _tracer: tracing.Tracer | None = None

    def __post_init__(self) -> None:
        check_credentials()
        self._tracer = tracing.make_safe_tracer(self._tracer or tracing.get_tracer())
        if self._client is None:
            from openai import OpenAI

            base = os.environ[BASE_URL_VAR].rstrip("/")
            if not base.endswith(GATEWAY_SUFFIX):
                base += GATEWAY_SUFFIX
            self._client = OpenAI(base_url=base, api_key=os.environ[API_KEY_VAR])

    # ── the retry loop ─────────────────────────────────────────────────────

    def _ask(
        self,
        prompt: prompts.ModelPrompt,
        schema: type[T],
        validate: Callable[[T], None] | None = None,
    ) -> tuple[T, bool]:
        """Ask once, validate, and retry twice with the error fed back.

        Silent unless all three fail. The caller then raises a RUNTIME warning and redraws
        the previous screen, so nothing already decided is lost.

        Returns the result and whether a retry was needed — a first-attempt success is `False`,
        anything that took a correction is `True`. `_step` uses the flag to decide whether the
        model's intro can be trusted in front of the user.
        """
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        last_error: Exception | None = None
        last_output: str | None = None
        tracer = self._tracer or tracing.NoopTracer()
        call_trace = tracer.start_call(
            name=prompt.name,
            model=self.model,
            session_id=self.session_id,
            messages=[dict(message) for message in messages],
        )

        try:
            for attempt in range(ATTEMPTS):
                attempt_trace = call_trace.start_attempt(
                    attempt=attempt + 1,
                    messages=[dict(message) for message in messages],
                    model=self.model,
                )
                started = time.perf_counter()
                try:
                    response = self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema.__name__,
                                "schema": schema.model_json_schema(),
                                "strict": True,
                            },
                        },
                    )
                    text = response.choices[0].message.content or ""
                    last_output = text
                    usage = tracing.usage_details_from_response(response)
                except Exception as exc:
                    attempt_trace.finish(
                        output="",
                        usage=None,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        error=str(exc),
                    )
                    raise

                try:
                    result = schema.model_validate_json(text)
                    if validate is not None:
                        validate(result)
                except (ValidationError, PatchValueError) as exc:
                    attempt_trace.finish(
                        output=text,
                        usage=usage,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        error=str(exc),
                    )
                    last_error = exc
                    if attempt < ATTEMPTS - 1:
                        # Feed the failure back rather than re-asking blind.
                        messages += [
                            {"role": "assistant", "content": text},
                            {
                                "role": "user",
                                "content": (
                                    "That didn't validate against the schema:\n"
                                    f"{exc}\n\nReturn corrected JSON only."
                                ),
                            },
                        ]
                else:
                    attempt_trace.finish(
                        output=text,
                        usage=usage,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                    return result, attempt > 0

            raise ModelOutputError(
                f"The model returned output I couldn't read, {ATTEMPTS} times running. "
                f"Last error: {last_error}"
            )
        finally:
            call_trace.finish(output=last_output)

    def _step(self, prompt: prompts.ModelPrompt, profile: ProductProfile) -> StepResult:
        result, recovered = self._ask(
            prompt,
            StepResult,
            validate=lambda candidate: validate_model_patches(
                profile, candidate.patches
            ),
        )
        # A recovered turn's intro tends to narrate the correction it just made — detail the
        # user should never see. Drop it and let the driver fall back to its neutral per-step
        # default; the patches, which are the real output, are kept either way.
        if recovered:
            result.message = ""
        return result

    # ── the interview ──────────────────────────────────────────────────────

    def clarify(
        self,
        profile: ProductProfile,
        history: list[Turn],
        phase: ClarifyPhase = "product",
    ) -> ClarifyResult:
        result, _ = self._ask(
            prompts.clarify(profile, history, phase),
            ClarifyResult,
            validate=lambda candidate: validate_model_patches(
                profile, candidate.patches
            ),
        )
        return result

    def draft_behaviours(
        self, profile: ProductProfile, history: list[Turn]
    ) -> StepResult:
        return self._step(prompts.behaviours(profile, history), profile)

    def draft_criteria(self, profile: ProductProfile) -> StepResult:
        return self._step(prompts.criteria(profile), profile)

    def draft_personas(self, profile: ProductProfile) -> StepResult:
        return self._step(prompts.personas(profile), profile)

    def draft_scenarios(self, profile: ProductProfile) -> StepResult:
        return self._step(prompts.scenarios(profile), profile)

    def chat(
        self, profile: ProductProfile, step: str, text: str, target: str | None
    ) -> StepResult:
        return self._step(prompts.chat(profile, step, text, target), profile)

    def suggest_criterion(
        self, profile: ProductProfile, behaviour_id: str
    ) -> StepResult:
        return self._step(
            prompts.suggest_criterion(profile, behaviour_id),
            profile,
        )

    # ── embeddings, for the matcher ────────────────────────────────────────

    def embed(
        self, texts: list[str], model: str = "gemini-embedding-001"
    ) -> list[list[float]]:
        response = self._client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]
