"""Finding Consistency metric (M-ORCA-*)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._finding_deduplication import _is_multi_agent_trace
from ._judge import _get_judge_model


class FindingConsistencyMetric(MetisTurnMetric):
    """No contradictions in multi-agent synthesis?

    Extract+judge: checks whether the final response contains conflicting statements.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
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
                name="Finding Consistency",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator's "
                    "response contains contradictions.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "synthesized response.\n\n"
                    "Check:\n"
                    "1. Are there any statements that "
                    "contradict each other?\n"
                    "2. If conflicting information exists, is "
                    "it explicitly flagged or resolved?\n"
                    "3. Are numbers, dates, or claims "
                    "consistent throughout?\n\n"
                    "Score 1.0 if fully consistent (no "
                    "contradictions). "
                    "Score 0.5 if a minor inconsistency exists "
                    "but is flagged. "
                    "Score 0.0 if clear contradictions are "
                    "present and unresolved." + EVIDENCE_INSTRUCTION
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
        if not _is_multi_agent_trace(test_case):
            return mark_skipped(
                self, "Single-agent or direct response (consistency N/A)"
            )

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
        return "Finding Consistency"

    def is_successful(self) -> bool:
        return self.success is True
