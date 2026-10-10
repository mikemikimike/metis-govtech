"""Direct Mode Escape grader (M-ORCA-23)."""

from typing import Any, ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from ._extraction import get_session_turns

_ESCAPE_TOKEN = "/agent"


class DirectModeEscapeGrader(BaseConversationalMetric):
    """Did the user escape routed mode with /agent after leader routing?

    Deterministic over the session timeline. Applicable only once the leader
    has routed to a specialist; fails when a subsequent user turn invokes
    ``/agent`` to bypass the selected path. Skips when no leader routing
    occurred (the criterion is not triggered).
    """

    tags: ClassVar[tuple[str, ...]] = ("orchestration", "session-level", "code-graded")

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: ConversationalTestCase) -> float:
        turns = get_session_turns(test_case)

        routing_index = next(
            (t.index for t in turns if t.role == "assistant" and t.routed_to),
            None,
        )
        if routing_index is None:
            self.skipped = True
            self.score = 1.0
            self.success = True
            self.reason = (
                "SKIPPED — no leader routing event observed in the session; "
                "direct-mode escape is not applicable."
            )
            return self.score

        escape_turn = next(
            (
                t
                for t in turns
                if t.index > routing_index
                and t.role == "user"
                and _ESCAPE_TOKEN in t.content.lower()
            ),
            None,
        )
        escaped = escape_turn is not None
        self.score = 0.0 if escaped else 1.0
        self.success = not escaped
        if escaped:
            evidence = (
                f"leader routed at turn {routing_index}; user turn "
                f"{escape_turn.index} invoked {_ESCAPE_TOKEN!r} → routing path bypassed."
            )
        else:
            evidence = (
                f"leader routed at turn {routing_index}; no later user turn "
                f"invoked {_ESCAPE_TOKEN!r} → routing path kept."
            )
        self.reason = evidence
        return self.score

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Direct Mode Escape"

    def is_successful(self) -> bool:
        return self.success is True
