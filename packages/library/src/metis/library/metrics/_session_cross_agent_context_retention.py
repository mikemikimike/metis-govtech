"""Session Cross-Agent Context Retention metric (M-ORCA-20)."""

from typing import ClassVar

from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    MultiTurnParams,
)

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisSessionMetric,
    _ContextAwareConversationalGEval,
)
from ._judge import _get_judge_model


class SessionCrossAgentContextRetentionMetric(MetisSessionMetric):
    """Context from earlier agent turns preserved across agent switches.

    Judge-graded session variant. Scores 1.0 automatically when only one agent
    was used (no switch to evaluate). For per-turn code-graded variant see
    ``orchestration.CrossAgentContextRetentionMetric``.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "session-level",
        "judge-graded",
    )

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Cross-Agent Context Retention",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether context is preserved when the orchestrator switches "
                    "between different subagents across turns.\n\n"
                    "You will see the full conversation with tool calls. Look for "
                    "'delegate_task_to_member' calls to identify "
                    "which agent handled each turn.\n\n"
                    "Check:\n"
                    "1. When agent A produced results in turn N, does "
                    "the orchestrator carry "
                    "those results into the delegation to agent B in "
                    "turn N+k?\n"
                    "2. Are file references, analytical findings, or "
                    "user preferences from "
                    "earlier agent turns available to later agents?\n"
                    "3. Does the user have to repeat information that "
                    "was already established?\n\n"
                    "Score 1.0 if context flows seamlessly across agent switches. "
                    "Score 0.5 if mostly preserved but minor details lost. "
                    "Score 0.0 if the orchestrator clearly lost context between agents. "
                    "If only one agent was used (no switch), score 1.0."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Cross-Agent Context Retention"

    def is_successful(self) -> bool:
        return self.success is True
