"""Session Synthesis Faithfulness metric (M-ORCA-22)."""

from typing import ClassVar

from ._base import EVIDENCE_INSTRUCTION, MetisSessionMetric, _ContextAwareConversationalGEval, mark_skipped

from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    MultiTurnParams,
)

from ._judge import _get_judge_model

def _has_delegation(test_case: ConversationalTestCase) -> bool:
    """Check whether any assistant turn has a delegate_task_to_member tool call."""
    for turn in test_case.turns:
        if turn.role == "assistant" and turn.tools_called:
            for tc in turn.tools_called:
                if tc.name == "delegate_task_to_member":
                    return True
    return False

class SessionSynthesisFaithfulnessMetric(MetisSessionMetric):
    """Key facts from subagent output preserved without distortion.

    Wraps ConversationalGEval with a pre-flight check: skips if no
    delegate_task_to_member call exists (direct-handle traces have nothing to
    synthesise). When delegation is present, the judge sees the full tool call
    history and checks faithfulness directly — no adapter pre-extraction needed.
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
                name="Synthesis Faithfulness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator's "
                    "final response faithfully represents "
                    "what the subagent(s) actually "
                    "produced.\n\n"
                    "You will see the full conversation "
                    "including all tool calls. "
                    "Look for tool calls named "
                    "'delegate_task_to_member' — the "
                    "OUTPUT of these "
                    "calls is what the subagent returned. "
                    "The final assistant message is what "
                    "Orca synthesised and delivered to "
                    "the user.\n\n"
                    "Check:\n"
                    "1. Are key facts, numbers, and "
                    "findings from the subagent output "
                    "present "
                    "in the final response? (no silent "
                    "omission of material results)\n"
                    "2. Does the final response introduce "
                    "any claims NOT supported by the "
                    "subagent output? (no fabrication)\n"
                    "3. Are the subagent's conclusions "
                    "preserved accurately — not reversed, "
                    "overstated, or understated?\n\n"
                    "Score 1.0 if the synthesis is fully "
                    "faithful. "
                    "Score 0.5 if mostly faithful but a "
                    "significant caveat or result was "
                    "dropped. "
                    "Score 0.0 if the final response "
                    "fabricates claims or materially "
                    "contradicts "
                    "what the subagent produced.\n\n"
                    "Quote the specific subagent output "
                    "and the final response text that "
                    "most "
                    "influenced your score." + EVIDENCE_INSTRUCTION
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
            return mark_skipped(self, "No delegation in this session")

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
            return mark_skipped(self, "No delegation in this session")

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Synthesis Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
