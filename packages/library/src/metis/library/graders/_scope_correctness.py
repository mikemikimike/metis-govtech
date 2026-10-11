"""Scope Correctness grader (M-DA-2)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisTurnGrader, _ContextAwareGEval
from ._judge import _get_judge_model


class ScopeCorrectnessGrader(MetisTurnGrader):
    """Analyses exactly what the user asked for?"""

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
                name="Scope Correctness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the Data Analyst agent analysed "
                    "exactly what the user asked for — "
                    "no more, no less.\n\n"
                    "The 'input' is the user's request specifying what "
                    "to analyse. "
                    "The 'actual_output' is the analysis result "
                    "delivered.\n\n"
                    "Check:\n"
                    "1. Are all quantities/metrics the user asked for "
                    "present in the output?\n"
                    "2. Did the agent add unrequested analyses "
                    "(scope creep)?\n"
                    "3. Did the agent narrow the scope and miss "
                    "something the user asked for?\n\n"
                    "Score 1.0 if scope is exact. When scoring 1.0, "
                    "state ONLY: "
                    "'Scope matches request — no over/under-analysis "
                    "detected.' "
                    "Do not describe report structure or formatting.\n"
                    "Score 0.5 if minor additions or omissions that "
                    "don't mislead — "
                    "quote what was added or missed.\n"
                    "Score 0.0 if significant scope violation — quote "
                    "the specific over- or under-reach." + EVIDENCE_INSTRUCTION
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
        return "Scope Correctness"

    def is_successful(self) -> bool:
        return self.success is True
