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

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from metis.wizard.application import prompts
from metis.wizard.application.interviewer import (
    InterviewerOutputError,
    InterviewerUnavailable,
)
from metis.wizard.contracts.output import ClarifyResult, StepResult
from metis.wizard.contracts.session_state import Turn
from metis.wizard.domain.applier import PatchValueError, validate_model_patches
from metis.wizard.domain.patch import PatchOrigin
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

    def __post_init__(self) -> None:
        check_credentials()
        if self._client is None:
            from openai import OpenAI

            base = os.environ[BASE_URL_VAR].rstrip("/")
            if not base.endswith(GATEWAY_SUFFIX):
                base += GATEWAY_SUFFIX
            self._client = OpenAI(base_url=base, api_key=os.environ[API_KEY_VAR])

    # ── the retry loop ─────────────────────────────────────────────────────

    def _ask(
        self,
        system: str,
        user: str,
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
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None

        for attempt in range(ATTEMPTS):
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
            try:
                result = schema.model_validate_json(text)
                if validate is not None:
                    validate(result)
                return result, attempt > 0
            except (ValidationError, PatchValueError) as exc:
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

        raise ModelOutputError(
            f"The model returned output I couldn't read, {ATTEMPTS} times running. "
            f"Last error: {last_error}"
        )

    def _step(self, system: str, user: str, profile: ProductProfile) -> StepResult:
        result, recovered = self._ask(
            system,
            user,
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
        # Origin is stamped by the code that builds a patch. Anything arriving here is the
        # model's, whatever it claims — `sanitise` in the driver enforces it again.
        result.patches = [
            patch.model_copy(update={"origin": PatchOrigin.MODEL})
            for patch in result.patches
        ]
        return result

    # ── the interview ──────────────────────────────────────────────────────

    def clarify(self, profile: ProductProfile, history: list[Turn]) -> ClarifyResult:
        # No user-facing intro to protect here — ClarifyResult carries only `done` and the
        # next `question`, so the recovery flag is discarded.
        result, _ = self._ask(
            prompts.system_prompt(),
            prompts.clarify_user(profile, history),
            ClarifyResult,
        )
        return result

    def draft_behaviours(
        self, profile: ProductProfile, history: list[Turn]
    ) -> StepResult:
        return self._step(
            prompts.system_prompt(), prompts.behaviours_user(profile, history), profile
        )

    def draft_criteria(self, profile: ProductProfile) -> StepResult:
        return self._step(
            prompts.system_prompt(), prompts.criteria_user(profile), profile
        )

    def draft_personas(self, profile: ProductProfile) -> StepResult:
        return self._step(
            prompts.system_prompt(), prompts.personas_user(profile), profile
        )

    def draft_tasks(self, profile: ProductProfile) -> StepResult:
        return self._step(prompts.system_prompt(), prompts.tasks_user(profile), profile)

    def chat(
        self, profile: ProductProfile, step: str, text: str, target: str | None
    ) -> StepResult:
        return self._step(
            prompts.system_prompt(),
            prompts.chat_user(profile, step, text, target),
            profile,
        )

    def suggest_criterion(
        self, profile: ProductProfile, behaviour_id: str
    ) -> StepResult:
        return self._step(
            prompts.system_prompt(),
            prompts.suggest_criterion_user(profile, behaviour_id),
            profile,
        )

    # ── embeddings, for the matcher ────────────────────────────────────────

    def embed(
        self, texts: list[str], model: str = "gemini-embedding-001"
    ) -> list[list[float]]:
        response = self._client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]


def _profile_json(profile: ProductProfile) -> str:
    """What the model reads. Deliberately the profile, not the transcript.

    Steps after clarify build their prompts from the document rather than the conversation,
    which is why architectural detail has to be promoted into `product.architecture` to
    survive at all.
    """
    return json.dumps(profile.model_dump(mode="json"), indent=2)
