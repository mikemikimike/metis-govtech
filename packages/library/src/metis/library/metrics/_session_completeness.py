"""Session Completeness metric."""

from typing import Any, ClassVar

from deepeval.metrics import (
    ConversationCompletenessMetric as _ConversationCompletenessMetric,
)
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    Turn,
)

from ._base import MetisSessionMetric
from ._judge import _get_judge_model


class SessionCompletenessMetric(MetisSessionMetric):
    """Did the session deliver what the user came for?

    Wraps DeepEval's built-in ConversationCompletenessMetric. Evaluates
    whether the multi-turn conversation ultimately achieved the user's goal —
    a session-level pass/fail that no per-turn metric captures.

    ConversationCompletenessMetric is referenceless: it infers the expected
    outcome from the conversation itself, so no annotation is needed.
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
        self._metric = None

    def _get_metric(self) -> _ConversationCompletenessMetric:
        if self._metric is None:
            self._metric = _ConversationCompletenessMetric(
                threshold=self.threshold,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def _strip_tool_calls(
        self, test_case: ConversationalTestCase
    ) -> ConversationalTestCase:
        """ConversationCompletenessMetric JSON-serializes turns internally.

        ToolCall objects are not JSON-serializable, so we pass a copy of the
        test case with tools_called stripped — completeness only needs turn
        content to judge whether the user's goal was achieved.
        """
        stripped_turns = [Turn(role=t.role, content=t.content) for t in test_case.turns]
        return ConversationalTestCase(turns=stripped_turns)

    def measure(self, test_case: ConversationalTestCase) -> float:
        metric = self._get_metric()
        metric.measure(self._strip_tool_calls(test_case))
        self.score = metric.score
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Session Completeness"

    def is_successful(self) -> bool:
        return self.success is True
