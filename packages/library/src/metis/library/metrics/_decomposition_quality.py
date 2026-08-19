"""Decomposition Quality metric (M-ORCA-*)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisTurnMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class DecompositionQualityMetric(MetisTurnMetric):
    """Multi-intent request correctly decomposed into sub-tasks?

    Extract+judge: evaluates whether Orca correctly identifies and orders
    sub-tasks from a multi-intent request.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "judge-graded",
    )

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Decomposition Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate how well the orchestrator "
                    "decomposed a multi-intent request.\n\n"
                    "The 'input' is the user's request "
                    "containing multiple intents.\n"
                    "The 'actual_output' is the orchestrator's "
                    "response showing how it handled the "
                    "request.\n\n"
                    "Check:\n"
                    "1. Were all distinct intents identified? "
                    "(no intent missed)\n"
                    "2. Were they ordered logically? "
                    "(dependencies respected — e.g. analyse "
                    "before present)\n"
                    "3. Were they executed appropriately? "
                    "(right subagent for each, or direct "
                    "handle)\n\n"
                    "Score 1.0 if all intents captured and "
                    "logically ordered. "
                    "Score 0.5 if intents captured but ordering "
                    "suboptimal. "
                    "Score 0.0 if an intent was missed entirely "
                    "or ordering is clearly wrong. "
                    "If the request has only one intent, "
                    "score 1.0." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
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
        return "Decomposition Quality"

    def is_successful(self) -> bool:
        return self.success is True
