"""Session Step Efficiency metric (M-UNI-6)."""

from typing import ClassVar

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
)

from ._base import mark_skipped


class SessionStepEfficiencyMetric(BaseConversationalMetric):
    """Task completed in near-minimum tool calls across session?

    Counts total tool calls across all assistant turns. Without an annotation
    for expected_minimum, reports the count and skips.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
        "session-level",
        "code-graded",
    )

    def __init__(self, threshold: float = 1.0, max_ratio: float = 1.3):
        self.threshold = threshold
        self.max_ratio = max_ratio
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: ConversationalTestCase) -> float:
        total_calls = 0
        for turn in test_case.turns:
            if turn.role == "assistant" and turn.tools_called:
                total_calls += len(turn.tools_called)

        expected_minimum = None
        if test_case.metadata and "expected_minimum_steps" in test_case.metadata:
            expected_minimum = test_case.metadata["expected_minimum_steps"]

        if expected_minimum is None:
            return mark_skipped(
                self,
                f"{total_calls} total tool call(s) across session, no minimum annotated",
            )

        if expected_minimum == 0:
            self.score = 1.0 if total_calls == 0 else 0.0
            self.reason = f"{total_calls} tool call(s), expected 0"
        else:
            ratio = total_calls / expected_minimum
            self.score = 1.0 if ratio <= self.max_ratio else 0.0
            self.reason = f"{total_calls} tool call(s) vs {expected_minimum} minimum (ratio: {ratio:.2f}, max: {self.max_ratio})"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Step Efficiency (session)"

    def is_successful(self) -> bool:
        return self.success is True
