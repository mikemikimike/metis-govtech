"""M-UNI-8: Clarification Precision metric."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model
from ._types import LlmTestCaseMetadata


class ClarificationPrecisionMetric(MetisTurnMetric):
    """All questions necessary and no needed question omitted?

    Extract+judge: extracts clarification questions from the trace and judges
    whether they are precisely calibrated — necessary and complete.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Clarification Precision",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the quality of clarification "
                    "questions the agent asked.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' contains the "
                    "clarification question(s) the agent "
                    "asked.\n\n"
                    "Check:\n"
                    "1. Necessity: Is every question "
                    "required to proceed? (no "
                    "superfluous questions)\n"
                    "2. Completeness: Are there obvious "
                    "missing questions the agent should "
                    "have asked?\n"
                    "3. Specificity: Are questions "
                    "precise enough to get actionable "
                    "answers?\n\n"
                    "Score 1.0 if all questions are "
                    "necessary, none are missing, and "
                    "they're specific. "
                    "Score 0.5 if mostly right but one "
                    "superfluous or one missing "
                    "question. "
                    "Score 0.0 if asks irrelevant things "
                    "or misses critical information "
                    "needs." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(LlmTestCaseMetadata, test_case.metadata)
        clarifications = metadata.get("clarification_requests", [])

        if not clarifications:
            return mark_skipped(self, "No clarification questions asked")

        questions_text = "\n".join(
            str(c.output or c.input or c) for c in clarifications
        )
        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=questions_text,
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(judge_tc)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Clarification Precision"

    def is_successful(self) -> bool:
        return self.success is True
