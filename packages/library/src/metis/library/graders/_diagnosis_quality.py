"""M-UNI-5: Diagnosis Quality grader."""

from typing import Any, ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnGrader,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model
from ._types import LlmTestCaseMetadata, OrcaChatMetadata


class DiagnosisQualityGrader(MetisTurnGrader):
    """Root cause identified before fix attempted?

    Extract+judge: extracts error observations and the agent's response,
    then judges whether the agent diagnosed the root cause before attempting a fix.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
        "per-turn",
        "judge-graded",
    )

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Diagnosis Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the agent correctly "
                    "diagnosed the root cause of a "
                    "failure "
                    "before attempting a fix.\n\n"
                    "The 'input' is the user's request "
                    "that triggered an error.\n"
                    "The 'actual_output' is the agent's "
                    "response including its diagnosis "
                    "and actions.\n\n"
                    "Check:\n"
                    "1. Does the agent identify what went "
                    "wrong (the root cause), not just "
                    "the symptom?\n"
                    "2. Does the diagnosis appear BEFORE "
                    "the fix attempt in the response?\n"
                    "3. Is the stated root cause "
                    "plausible given the error?\n\n"
                    "Score 1.0 if root cause correctly "
                    "identified before fix. "
                    "Score 0.5 if diagnosis is present "
                    "but superficial or after the fix "
                    "attempt. "
                    "Score 0.0 if no diagnosis — agent "
                    "jumps straight to retrying or "
                    "guessing." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _has_error(self, test_case: LLMTestCase) -> bool:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata)
        if metadata.get("had_error"):
            return True
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )
        if chat_meta.had_error:
            return True
        observations = metadata.get("observations", [])
        for obs in observations:
            if obs.get("type") != "TOOL":
                continue
            obs_meta = obs.get("metadata") or {}
            if obs_meta.get("error"):
                return True
            level = obs.get("level") or ""
            if level.upper() == "ERROR":
                return True
        return False

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        if not self._has_error(test_case):
            return mark_skipped(self, "No error observed in trace")

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Diagnosis Quality"

    def is_successful(self) -> bool:
        return self.success is True
