"""Cancellation metric (M-UNI-21)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnMetric, mark_skipped
from ._extraction import get_chat_metadata, get_metadata


class CancellationMetric(MetisTurnMetric):
    """Did the user manually cancel an active task?

    Deterministic. Applicable only when the engine reports that cancellation
    was observable for the turn (``cancellation_available`` is not None).
    Fails when the turn's chat metadata records a manual cancellation; passes
    otherwise. Skips when cancellation availability is unknown.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "code-graded")
    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = get_metadata(test_case)
        available = metadata.get("cancellation_available")

        if available is None:
            return mark_skipped(
                self,
                "cancellation availability is unknown for this turn; "
                "the no-cancellation criterion cannot be assessed.",
            )

        was_cancelled = get_chat_metadata(test_case).was_cancelled
        self.score = 0.0 if was_cancelled else 1.0
        self.success = not was_cancelled
        verdict = (
            "the user manually cancelled the active task"
            if was_cancelled
            else "no manual cancellation of an active task"
        )
        self.reason = f"{verdict} (was_cancelled={was_cancelled})."
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Cancellation"

    def is_successful(self) -> bool:
        return self.success is True
