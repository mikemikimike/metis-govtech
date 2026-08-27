"""Abandonment metric (M-UNI-20)."""

from typing import Any, ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from ._extraction import get_session_metadata, get_session_turns

# Stop reasons that indicate the user walked away from a started workflow.
_ABANDONED = {"user_abandoned", "abandoned"}
# Stop reasons that are external/inconclusive — never attributed to the user.
_EXTERNAL = {"timeout", "system_error", "error", "unknown", ""}


class AbandonmentMetric(BaseConversationalMetric):
    """Did the user abandon a started workflow before it terminated?

    Deterministic over the engine-supplied ``stop_reason``. Passes when a
    started workflow reached a terminal outcome; fails only on an explicit
    ``user_abandoned`` stop reason. Skips when no work started or when the
    cause is external (timeout, system error, unknown).
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "session-level", "code-graded")

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: ConversationalTestCase) -> float:
        metadata = get_session_metadata(test_case)
        stop_reason = metadata.get("stop_reason")
        turns = get_session_turns(test_case)
        started_work = any(
            t.role == "assistant" and (t.tool_names or t.routed_to) for t in turns
        )

        if not started_work:
            self.skipped = True
            self.score = 1.0
            self.success = True
            self.reason = (
                "SKIPPED — no started workflow observed in the session "
                "(no assistant tool call or routing); abandonment is not applicable."
            )
            return self.score

        normalized = (stop_reason or "").lower()
        if stop_reason is None or normalized in _EXTERNAL:
            self.skipped = True
            self.score = 1.0
            self.success = True
            self.reason = (
                f"SKIPPED — stop reason {stop_reason!r} is external or unavailable; "
                "user abandonment cannot be attributed."
            )
            return self.score

        abandoned = normalized in _ABANDONED
        self.score = 0.0 if abandoned else 1.0
        self.success = not abandoned
        verdict = (
            "user abandoned the started workflow"
            if abandoned
            else "workflow reached a terminal outcome without user abandonment"
        )
        self.reason = f"{verdict} (stop_reason={stop_reason!r})."
        return self.score

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Abandonment"

    def is_successful(self) -> bool:
        return self.success is True
