"""M-UNI-11: Constraint Adherence metric."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class ConstraintAdherenceMetric(MetisMetric):
    """All explicit constraints and negative instructions respected?

    Extract+judge: checks whether user-specified constraints are honored.
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
                name="Constraint Adherence",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the agent respected "
                    "all explicit constraints and "
                    "negative instructions from the "
                    "user.\n\n"
                    "SYSTEM CONTEXT: This agent is an "
                    "orchestrator that delegates tasks "
                    "to "
                    "specialised subagents. When the "
                    "user says 'analyse this file' or "
                    "'cluster "
                    "this data', the orchestrator's job "
                    "is to delegate to the right "
                    "subagent — "
                    "this IS completing the task. "
                    "Presenting a configuration form "
                    "before execution "
                    "is NORMAL WORKFLOW, not a failure "
                    "to perform the task.\n\n"
                    "IMPORTANT: Only evaluate EXPLICIT "
                    "constraints — things the user said "
                    "with "
                    "words like 'do not', 'must', "
                    "'only', 'no more than', 'without', "
                    "'exclude'. "
                    "Do NOT treat the user's task "
                    "request itself as a 'constraint.' "
                    "The task "
                    "is being delegated and executed — "
                    "evaluate whether explicit "
                    "restrictions "
                    "within that task are honoured.\n\n"
                    "The 'input' is the user's "
                    "request.\n"
                    "The 'actual_output' is the agent's "
                    "response.\n\n"
                    "Check:\n"
                    "1. Identify all explicit "
                    "constraints in the input (format "
                    "restrictions, "
                    "exclusions, limits, negative "
                    "instructions)\n"
                    "2. Verify each constraint is satisfied in the output\n"
                    "3. If no explicit constraints exist, score 1.0\n\n"
                    "Score 1.0 if all constraints respected or no constraints present. "
                    "Score 0.5 if minor violation of a soft constraint. "
                    "Score 0.0 if a hard constraint is clearly violated."
                    + EVIDENCE_INSTRUCTION
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
        return "Constraint Adherence"

    def is_successful(self) -> bool:
        return self.success is True
