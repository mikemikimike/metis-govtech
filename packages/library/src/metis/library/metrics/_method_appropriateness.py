"""Method Appropriateness metric (M-DA-4)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisTurnMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class MethodAppropriatenessMetric(MetisTurnMetric):
    """Statistical method suited to data distribution?"""

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
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

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
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
        return "Method Appropriateness"

    def is_successful(self) -> bool:
        return self.success is True
