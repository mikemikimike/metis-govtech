"""Method Appropriateness metric (M-DA-4)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class MethodAppropriatenessMetric(SyncBaseMetric):
    """Statistical method suited to data distribution?"""

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Method Appropriateness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the Data Analyst chose an "
                    "appropriate analytical method.\n\n"
                    "The 'input' is the user's analytical question.\n"
                    "The 'actual_output' describes the analysis "
                    "performed and its results.\n\n"
                    "Check:\n"
                    "1. Is the chosen method suited to the data type? "
                    "(e.g. don't use Pearson on "
                    "non-linear relationships, don't use t-test on "
                    "non-normal small samples)\n"
                    "2. Is the method appropriate for the question "
                    "being asked?\n"
                    "3. Are there obvious better alternatives the "
                    "agent should have used?\n\n"
                    "IMPORTANT: If the task does not involve a "
                    "specific quantitative or "
                    "statistical method (e.g. it is a document "
                    "summary, a report of pre-computed "
                    "figures, or a simple aggregation), score 1.0 "
                    "and state ONLY: "
                    "'No statistical method choice required for this "
                    "task type.'\n"
                    "Score 1.0 if method is well-suited — state the "
                    "method used and why it fits.\n"
                    "Score 0.5 if acceptable but a better method "
                    "exists — name the better alternative.\n"
                    "Score 0.0 if method is clearly inappropriate — "
                    "explain why." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Method Appropriateness"

    def is_successful(self) -> bool:
        return self.success is True
