"""Slide Protocol Ordering metric (M-SM-1)."""

from typing import Any, ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from ._extraction import SessionTurn, get_session_turns

# Tool names that build the deck.
_DECK_TOOLS = ("make_ppt", "create_deck", "generate_deck", "build_deck")
# Assistant-message hints that a style preference was solicited.
_STYLE_HINTS = (
    "style",
    "theme",
    "template",
    "design",
    "look and feel",
    "color scheme",
    "colour scheme",
    "branding",
)


def _first_deck_turn(turns: list[SessionTurn]) -> int | None:
    wanted = {t.lower() for t in _DECK_TOOLS}
    for turn in turns:
        if any(name.lower() in wanted for name in turn.tool_names):
            return turn.index
    return None


def _first_style_turn(turns: list[SessionTurn], before: int) -> int | None:
    for turn in turns:
        if turn.index >= before or turn.role != "assistant":
            continue
        content = turn.content.lower()
        if any(hint in content for hint in _STYLE_HINTS):
            return turn.index
    return None


def _first_brief_turn(turns: list[SessionTurn], before: int) -> int | None:
    for turn in turns:
        if turn.index >= before:
            continue
        if any("brief" in name.lower() for name in turn.tool_names):
            return turn.index
        if turn.role == "assistant" and "brief" in turn.content.lower():
            return turn.index
    return None


class SlideProtocolOrderingMetric(BaseConversationalMetric):
    """Style asked before generation, brief before deck? (M-SM-1)

    Deterministic over the full session timeline. Passes only when a style
    preference is solicited before a brief is produced, and the brief precedes
    the deck-build call (style -> brief -> deck). Skips when no deck is built
    (the protocol is not triggered).
    """

    tags: ClassVar[tuple[str, ...]] = ("presentation", "session-level", "code-graded")

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: ConversationalTestCase) -> float:
        turns = get_session_turns(test_case)
        deck_turn = _first_deck_turn(turns)

        if deck_turn is None:
            self.skipped = True
            self.score = 1.0
            self.success = True
            self.reason = (
                "SKIPPED — no deck-build call observed in the session; slide "
                "protocol ordering is not applicable."
            )
            return self.score

        style_turn = _first_style_turn(turns, before=deck_turn)
        brief_turn = _first_brief_turn(turns, before=deck_turn)

        style_ok = style_turn is not None
        brief_ok = brief_turn is not None
        order_ok = style_ok and brief_ok and style_turn < brief_turn
        passed = style_ok and brief_ok and order_ok

        self.score = 1.0 if passed else 0.0
        self.success = passed

        if not style_ok:
            evidence = (
                f"deck built at turn {deck_turn}, but no style preference was "
                "asked before generation."
            )
        elif not brief_ok:
            evidence = (
                f"style asked at turn {style_turn}, deck built at turn "
                f"{deck_turn}, but no brief was produced before the deck."
            )
        elif not order_ok:
            evidence = (
                f"brief at turn {brief_turn} preceded the style question at "
                f"turn {style_turn}; required order is style -> brief -> deck."
            )
        else:
            evidence = (
                f"style asked at turn {style_turn}, brief at turn {brief_turn}, "
                f"deck built at turn {deck_turn} — correct order."
            )

        self.reason = evidence
        return self.score

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Slide Protocol Ordering"

    def is_successful(self) -> bool:
        return self.success is True
