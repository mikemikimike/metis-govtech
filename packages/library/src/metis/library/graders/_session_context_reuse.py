"""Session Context Reuse grader (M-UNI-3)."""

from typing import Any, ClassVar

from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    MultiTurnParams,
)

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisSessionGrader,
    _ContextAwareConversationalGEval,
)
from ._judge import _get_judge_model


class SessionContextReuseGrader(MetisSessionGrader):
    """Cached context used instead of re-asking?

    Identifies when the agent asks for information the user already provided in
    a prior turn. The judge quotes what was already established and what was
    redundantly re-asked.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
        "session-level",
        "judge-graded",
    )

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
                name="Context Reuse (session)",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the assistant asks the user for information that was "
                    "already provided in an earlier turn of this conversation.\n\n"
                    "You will see the full multi-turn conversation. Look for:\n"
                    "1. Facts the user stated in earlier turns (file names, preferences, "
                    "constraints, data descriptions, choices made)\n"
                    "2. Tool calls named 'request_user_input' in assistant turns — these are "
                    "the assistant asking the user a question\n\n"
                    "A REDUNDANT ask is when the assistant asks for something the user already "
                    "told it. For example:\n"
                    "- User said 'analyse sales.csv' in turn 1, "
                    "assistant asks 'which file?' in turn 3\n"
                    "- User chose 'detailed model' in turn 1, "
                    "assistant asks 'which model?' in turn 2\n\n"
                    "A NON-REDUNDANT ask is when the assistant "
                    "asks for NEW information not yet "
                    "established (e.g. asking about chart style "
                    "when only data analysis was discussed).\n\n"
                    "Score 1.0 if no redundant re-asks — every "
                    "question asks for genuinely new info. "
                    "Score 0.5 if one borderline case "
                    "(information was implied but not explicitly "
                    "stated). "
                    "Score 0.0 if the assistant clearly re-asks "
                    "for something the user already "
                    "provided.\n\n"
                    "In your reasoning, if there IS a redundant ask:\n"
                    "- Quote the original user statement that established the fact\n"
                    "- Quote the assistant's later question that re-asks for it\n"
                    "- Explain why this is redundant" + EVIDENCE_INSTRUCTION
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
        return "Context Reuse (session)"

    def is_successful(self) -> bool:
        return self.success is True
