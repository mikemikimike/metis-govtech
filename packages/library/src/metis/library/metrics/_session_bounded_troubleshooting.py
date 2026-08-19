"""Session Bounded Troubleshooting metric (M-UNI-16)."""

from typing import ClassVar

from ._base import MetisSessionMetric
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
)


class SessionBoundedTroubleshootingMetric(MetisSessionMetric):
    """Stops retrying after N failed attempts?

    Detects RETRY loops: consecutive calls to the same tool where the output
    indicates an error (contains 'error', 'traceback', 'exception', 'failed').
    A tool called many times with DIFFERENT successful outputs is fine.
    Only flags when the agent keeps hammering a failing operation.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
        "session-level",
        "code-graded",
    )

    ERROR_SIGNALS = [
        "error",
        "traceback",
        "exception",
        "failed",
        "errno",
        "permission denied",
    ]

    def __init__(self, threshold: float = 1.0, max_retries: int = 3):
        self.threshold = threshold
        self.max_retries = max_retries
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def _is_error_output(self, output) -> bool:
        if not output:
            return False
        text = str(output).lower()
        return any(sig in text for sig in self.ERROR_SIGNALS)

    def measure(self, test_case: ConversationalTestCase) -> float:
        # Collect all tool calls in order across all assistant turns
        all_calls = []
        for turn in test_case.turns:
            if turn.role == "assistant" and turn.tools_called:
                for tc in turn.tools_called:
                    all_calls.append(tc)

        if not all_calls:
            self.score = 1.0
            self.reason = "No tool calls in session"
            self.success = True
            return self.score or 0.0

        # Find consecutive error streaks per tool
        violations = []
        i = 0
        while i < len(all_calls):
            tc = all_calls[i]
            if self._is_error_output(tc.output):
                # Start counting consecutive errors for this tool
                streak_tool = tc.name
                streak_count = 1
                j = i + 1
                while (
                    j < len(all_calls)
                    and all_calls[j].name == streak_tool
                    and self._is_error_output(all_calls[j].output)
                ):
                    streak_count += 1
                    j += 1
                if streak_count > self.max_retries:
                    violations.append(
                        {
                            "tool": streak_tool,
                            "consecutive_errors": streak_count,
                        }
                    )
                i = j
            else:
                i += 1

        if not violations:
            self.score = 1.0
            self.reason = (
                "No unbounded retry loops detected (errors stay within retry limit)"
            )
        else:
            self.score = 0.0
            details = "; ".join(
                f"{v['tool']} failed {v['consecutive_errors']}x consecutively (limit: {self.max_retries})"
                for v in violations
            )
            self.reason = f"Retry loop detected: {details}"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Bounded Troubleshooting (session)"

    def is_successful(self) -> bool:
        return self.success is True
