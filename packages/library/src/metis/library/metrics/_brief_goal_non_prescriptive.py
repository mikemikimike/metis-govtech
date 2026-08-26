"""Brief Goal Non-Prescriptive metric (M-SM-6)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import extract_brief
from ._judge import _get_judge_model


class BriefGoalNonPrescriptiveMetric(MetisTurnMetric):
    """Goal is outcome-oriented, not dictating slide content? (M-SM-6)

    Judge-graded. Uses the extracted brief. Scores full marks when the deck
    goal states the desired outcome without prescribing specific slide
    content. Skips when no brief is observable.
    """

    tags: ClassVar[tuple[str, ...]] = ("presentation", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Brief Goal Non-Prescriptive",
                model=_get_judge_model(),
                criteria=(
                    "The brief's deck goal describes the desired outcome "
                    "without dictating specific slide content; judge whether "
                    "the goal field of the brief is outcome-oriented rather "
                    "than prescribing slide-by-slide content.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the extracted brief; the 'actual_output' is the agent's "
                    "response.\n\n"
                    "Focus on the brief's deck goal and assess whether it is "
                    "outcome-oriented (what the deck should achieve for its "
                    "audience) rather than prescriptive (dictating specific "
                    "slides, their order, or their exact content).\n\n"
                    "Score 1.0 when the goal states the desired outcome without "
                    "dictating slide content. "
                    "Score 0.5 when it is mostly outcome-oriented but drifts "
                    "into some content prescription. "
                    "Score 0.0 when the goal prescribes slide-by-slide content "
                    "instead of an outcome." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase, brief: str) -> LLMTestCase:
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=["Extracted brief:\n" + brief],
            metadata=test_case.metadata,
        )

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        brief = extract_brief(test_case)
        if not brief:
            return mark_skipped(
                self, "no brief observed; the deck goal cannot be assessed."
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, brief))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Brief Goal Non-Prescriptive"

    def is_successful(self) -> bool:
        return self.success is True
