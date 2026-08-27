"""Correction metric (M-UNI-19)."""

from typing import Any, ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    MultiTurnParams,
)

from ._base import EVIDENCE_INSTRUCTION, _ContextAwareConversationalGEval
from ._judge import _get_judge_model


class CorrectionMetric(BaseConversationalMetric):
    """Was the delivered result accepted without correction?

    Judge-graded over the full session. Locates where the agent delivers a
    result, then examines the next up-to-two user turns. Scores full marks
    only when the user accepts the result without correcting, redoing, or
    repeating the request.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "session-level", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareConversationalGEval:
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Correction-Free Acceptance",
                model=_get_judge_model(),
                criteria=(
                    "After the agent delivers a result, the user should accept "
                    "it without correcting it, asking for a redo, or repeating "
                    "the same request within the next two user turns; read the "
                    "conversation, find where the agent presents a deliverable, "
                    "then inspect the content of the next up-to-two user turns "
                    "for a correction, redo request, or repeat of the same "
                    "ask.\n\n"
                    "You will see the full conversation. Identify the turn "
                    "where the agent delivers a result or deliverable, then "
                    "look only at the next two user turns after it.\n\n"
                    "Assess whether, in those next two user turns, the user:\n"
                    "1. corrects the result (points out an error, asks to "
                    "change it), or\n"
                    "2. asks the agent to redo or regenerate it, or\n"
                    "3. repeats the same request (implying the result did not "
                    "satisfy it).\n\n"
                    "Score 1.0 when none of these occur — the user accepts the "
                    "result (moves on, thanks the agent, or makes a genuinely "
                    "new request). "
                    "Score 0.0 when the user corrects, redoes, or repeats the "
                    "request within the next two turns. "
                    "If the agent never delivers a result, score 1.0 (no "
                    "delivered result to reject)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[MultiTurnParams.CONTENT],
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
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Correction-Free Acceptance"

    def is_successful(self) -> bool:
        return self.success is True
