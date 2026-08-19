"""Session Conversation Faithfulness metric (M-UNI-18)."""

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


class SessionConversationFaithfulnessMetric(MetisSessionMetric):
    """Response does not contradict facts established in prior turns."""

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
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
                name="Conversation Faithfulness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the assistant's responses contradict facts established "
                    "earlier in the conversation.\n\n"
                    "You will see the full multi-turn conversation including all user messages "
                    "and assistant responses.\n\n"
                    "Check:\n"
                    "1. Identify factual claims the assistant made in earlier turns\n"
                    "2. Check if any later assistant response contradicts those claims\n"
                    "3. Check if any later response contradicts facts the user stated\n\n"
                    "Score 1.0 if fully consistent across all turns. "
                    "Score 0.5 if minor inconsistency that doesn't mislead. "
                    "Score 0.0 if clear contradiction between turns."
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
        return "Conversation Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
