"""First-Look Inspection and Cleaning metric (M-DA-20)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import get_executed_code
from ._judge import _get_judge_model


class FirstLookInspectionCleaningMetric(MetisTurnMetric):
    """Did the agent inspect and clean the data before analysing?

    Judge-graded (M-DA-20). Assesses whether the executed code inspects the
    data (shape/dtypes/head/missing/describe) and cleans it appropriately
    before computing results, without modifying files in ``uploads/``.
    Skips when no code execution is observable.
    """

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
                name="First-Look Inspection and Cleaning",
                model=_get_judge_model(),
                criteria=(
                    "Before computing results, the agent should inspect the "
                    "data (shape, dtypes, head, missing values, describe) and "
                    "apply appropriate cleaning, without modifying files in "
                    "uploads/; judge the Python code the agent executed and its "
                    "response for inspection steps, cleaning before analysis, "
                    "and no writes to uploads/.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the Python code the agent executed; the 'actual_output' "
                    "is the agent's response.\n\n"
                    "Assess three dimensions:\n"
                    "1. Inspection: Does the code examine the data before "
                    "analysis — shape, dtypes, head, missing values, and "
                    "describe (or clear equivalents)?\n"
                    "2. Cleaning before compute: Are appropriate cleaning "
                    "steps (dtype fixes, missing-value handling, dedup) done "
                    "before results are computed?\n"
                    "3. Uploads untouched: Does the code avoid writing to or "
                    "modifying files under uploads/?\n\n"
                    "Score 1.0 when it inspects, cleans before computing, and "
                    "leaves uploads/ unmodified. "
                    "Score 0.5 when inspection or cleaning is partial. "
                    "Score 0.0 when it computes without inspection/cleaning or "
                    "modifies uploads/." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase) -> LLMTestCase:
        code = get_executed_code(test_case)
        context = (
            ["Executed code:\n" + "\n\n".join(code)] if code else test_case.context
        )
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=context,
            metadata=test_case.metadata,
        )

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        if not get_executed_code(test_case):
            return mark_skipped(
                self,
                "no code execution observed; data inspection and "
                "cleaning cannot be assessed.",
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "First-Look Inspection and Cleaning"

    def is_successful(self) -> bool:
        return self.success is True
