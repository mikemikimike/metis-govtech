"""Session Task Decomposition Accuracy metric (M-ORCA-22)."""

from typing import ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    MultiTurnParams,
)

from ._base import EVIDENCE_INSTRUCTION, _ContextAwareConversationalGEval
from ._judge import _get_judge_model


def _has_delegation(test_case: ConversationalTestCase) -> bool:
    """Check whether any assistant turn has a delegate_task_to_member tool call."""
    for turn in test_case.turns:
        if turn.role == "assistant" and turn.tools_called:
            for tc in turn.tools_called:
                if tc.name == "delegate_task_to_member":
                    return True
    return False


class SessionTaskDecompositionAccuracyMetric(BaseConversationalMetric):
    """Correct subagents selected and delegated in logical sequence.

    Skips when no delegation occurred — direct-handle is correct behaviour,
    not a decomposition failure. Only evaluates when the orchestrator actually
    chose to use subagents.
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
                name="Task Decomposition Accuracy",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator "
                    "selected the correct subagents and "
                    "delegated tasks in a logical "
                    "sequence across the session.\n\n"
                    "You will see the full conversation "
                    "with tool calls. Look for "
                    "'delegate_task_to_member' calls to "
                    "see which agents were used and in "
                    "what order.\n\n"
                    "Check:\n"
                    "1. Were the right agents chosen for "
                    "each sub-task? (e.g. data-analyst "
                    "for "
                    "analysis, slide-maker for "
                    "presentations)\n"
                    "2. Was the ordering logical? (e.g. "
                    "analyse data BEFORE making a "
                    "presentation "
                    "of the results)\n"
                    "3. Were any unnecessary agents "
                    "invoked, or necessary agents "
                    "skipped?\n\n"
                    "Score 1.0 if correct agents in "
                    "correct order. "
                    "Score 0.5 if right agents but "
                    "suboptimal ordering. "
                    "Score 0.0 if wrong agents were "
                    "chosen or critical ordering was "
                    "violated." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        if not _has_delegation(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation in this session — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        if not _has_delegation(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation in this session — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Task Decomposition Accuracy"

    def is_successful(self) -> bool:
        return self.success is True
