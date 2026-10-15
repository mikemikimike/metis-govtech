"""The real interviewer, over the PlatformAI gateway.

The gateway is OpenAI-compatible, so the client is `OpenAI` with a `base_url` — and it serves
both chat and embeddings on one endpoint and key, which is why the matcher is not a second
integration.

The client is imported from `langfuse.openai`, Langfuse's drop-in for the OpenAI client.
Importing it patches the client so every chat and embedding call is recorded as a generation —
input, raw reply, model, token usage and latency — with no tracing code on the call path.
`_ask` is wrapped with `@observe`, so a call's three attempts nest under one trace named by the
Interview step. A caller that has an Interview ID can use it to group traces; the stateless
lifecycle normally records them ungrouped. Tracing is opt-in by environment: with no `LANGFUSE_*`
variables the drop-in disables itself and sends nothing, and it exports on a background thread, so
it never blocks or fails the Interview.

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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from langfuse import get_client, observe
from openai import APIError
from pydantic import BaseModel, ValidationError

from metis.wizard.application import prompts
from metis.wizard.application.interviewer import (
    InterviewContextBudgetError,
    InterviewerOutputError,
    InterviewerUnavailable,
)
from metis.wizard.application.readiness import missing_criteria_paths
from metis.wizard.contracts.output import ClarifyResult, StepResult
from metis.wizard.domain.applier import PatchValueError, validate_model_patches
from metis.wizard.domain.patch import PatchOp

if TYPE_CHECKING:
    from collections.abc import Callable

    from metis.wizard.contracts.interview_state import InterviewContext, Turn
    from metis.wizard.domain.specification import Specification

BASE_URL_VAR = "OPENAI_BASE_URL"
API_KEY_VAR = "OPENAI_API_KEY"
MODEL_VAR = "INTERVIEW_MODEL"

DEFAULT_MODEL = "gpt-5.6-luna"

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
    context_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("INTERVIEW_CONTEXT_TOKENS", "128000")
        )
    )
    output_tokens: int = field(
        default_factory=lambda: int(os.environ.get("INTERVIEW_OUTPUT_TOKENS", "16384"))
    )
    _client: Any = None
    interview_id: str | None = None

    def __post_init__(self) -> None:
        check_credentials()
        if not 0 < self.output_tokens < self.context_tokens:
            raise ValueError(
                "INTERVIEW_OUTPUT_TOKENS must be positive and below INTERVIEW_CONTEXT_TOKENS."
            )
        if self._client is None:
            # The drop-in traces every call; unconfigured it is a quiet no-op. The OpenAI client
            # does not connect on construction, so this stays offline until a call is made.
            from langfuse.openai import OpenAI

            # OPENAI_BASE_URL is the full OpenAI-compatible endpoint; the client uses it as given.
            self._client = OpenAI(
                base_url=os.environ[BASE_URL_VAR].rstrip("/"),
                api_key=os.environ[API_KEY_VAR],
            )

    # ── the retry loop ─────────────────────────────────────────────────────

    @observe
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

        `@observe` opens the trace; each attempt's `create` call nests under it as a generation.
        The trace is named by the interview step and, where known, carries the interview id, so one
        interview reads as one sequence. A call with no interview id is still recorded, ungrouped.
        """
        # `session_id=` is the Langfuse SDK's trace-grouping parameter. It stays empty when a
        # stateless caller has no Interview ID; the call is still traced.
        get_client().update_current_trace(
            name=prompt.name, session_id=self.interview_id
        )
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        last_error: Exception | None = None

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }
        for attempt in range(ATTEMPTS):
            # One token per UTF-8 byte is a conservative bound for byte-based model
            # tokenizers. Include schema, retry history, framing, and reserved output.
            input_bound = (
                len(
                    json.dumps(
                        {"messages": messages, "response_format": response_format},
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
                + 4096
            )
            if input_bound + self.output_tokens > self.context_tokens:
                raise InterviewContextBudgetError(
                    f"Request for {self.model} needs a conservative budget of "
                    f"{input_bound + self.output_tokens:,} tokens; configured context is "
                    f"{self.context_tokens:,}. No input was truncated. Set INTERVIEW_CONTEXT_TOKENS "
                    "to the provider's supported limit or reduce the documents."
                )
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=response_format,
                    max_completion_tokens=self.output_tokens,
                )
            except APIError as exc:
                raise InterviewerOutputError(
                    "The model gateway could not complete the request."
                ) from exc
            text = response.choices[0].message.content or ""

            try:
                result = schema.model_validate_json(text)
                if validate is not None:
                    validate(result)
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
            else:
                return result, attempt > 0

        raise ModelOutputError(
            f"The model returned output I couldn't read, {ATTEMPTS} times running. "
            f"Last error: {last_error}"
        )

    def _step(
        self,
        prompt: prompts.ModelPrompt,
        specification: Specification,
        context: InterviewContext | None = None,
        *,
        required_additions: frozenset[str] = frozenset(),
    ) -> StepResult:
        def validate(candidate: StepResult) -> None:
            validate_model_patches(
                specification,
                candidate.patches,
                allowed_fixture_names=set(context.document_names if context else []),
            )
            missing = required_additions - {
                patch.path for patch in candidate.patches if patch.op is PatchOp.ADD
            }
            if missing:
                raise PatchValueError(
                    "Return at least one ADD patch with a strict Criterion draft for each "
                    "of these current Specification paths: "
                    + ", ".join(sorted(missing))
                    + ". Use IDs from the current Specification, not IDs in source documents."
                )

        result, recovered = self._ask(prompt, StepResult, validate=validate)
        # A recovered turn's intro tends to narrate the correction it just made — detail the
        # user should never see. Drop it and let the driver fall back to its neutral per-step
        # default; the patches, which are the real output, are kept either way.
        if recovered:
            result.message = ""
        return result

    # ── the interview ──────────────────────────────────────────────────────

    def clarify(
        self,
        specification: Specification,
        history: list[Turn],
        context: InterviewContext | None = None,
    ) -> ClarifyResult:
        result, _ = self._ask(
            prompts.clarify(specification, history, context),
            ClarifyResult,
            validate=lambda candidate: validate_model_patches(
                specification,
                candidate.patches,
                allowed_fixture_names=set(
                    context.document_names if context is not None else []
                ),
            ),
        )
        return result

    def draft_behaviours(
        self,
        specification: Specification,
        history: list[Turn],
        context: InterviewContext | None = None,
    ) -> StepResult:
        return self._step(
            prompts.behaviours(specification, history, context), specification, context
        )

    def draft_criteria(
        self,
        specification: Specification,
        context: InterviewContext | None = None,
    ) -> StepResult:
        return self._step(
            prompts.criteria(specification, context),
            specification,
            context,
            required_additions=missing_criteria_paths(specification),
        )

    def draft_personas(
        self,
        specification: Specification,
        context: InterviewContext | None = None,
    ) -> StepResult:
        return self._step(
            prompts.personas(specification, context), specification, context
        )

    def draft_scenarios(
        self,
        specification: Specification,
        context: InterviewContext | None = None,
    ) -> StepResult:
        return self._step(
            prompts.scenarios(specification, context), specification, context
        )

    def chat(
        self,
        specification: Specification,
        step: str,
        text: str,
        target: str | None,
        context: InterviewContext | None = None,
    ) -> StepResult:
        return self._step(
            prompts.chat(specification, step, text, target, context),
            specification,
            context,
        )

    def suggest_criterion(
        self,
        specification: Specification,
        behaviour_id: str,
        context: InterviewContext | None = None,
    ) -> StepResult:
        return self._step(
            prompts.suggest_criterion(specification, behaviour_id, context),
            specification,
            context,
        )

    # ── embeddings, for the matcher ────────────────────────────────────────

    def embed(
        self, texts: list[str], model: str = "gemini-embedding-001"
    ) -> list[list[float]]:
        response = self._client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]
