"""M-UNI-6: Bounded Troubleshooting metric."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnMetric
from ._types import TraceMetadata


class BoundedTroubleshootingMetric(MetisTurnMetric):
    """Stops retrying after N attempts?

    Counts repeated calls to the same tool name in TOOL observations.
    For example, execute_python called 7 times suggests the agent kept
    retrying failed code. Passes if no single tool exceeds max_retries.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "code-graded")
    async_mode = False

    def __init__(self, threshold: float = 1.0, max_retries: int = 5):
        self.threshold = threshold
        self.max_retries = max_retries
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        retry_counts = metadata.get("retry_counts", {})
        tool_calls = metadata.get("tool_calls", [])

        # Also count from raw tool calls for completeness
        if not retry_counts and tool_calls:
            from collections import Counter

            counts = Counter(tc.get("name", "") for tc in tool_calls)
            retry_counts = {name: c for name, c in counts.items() if c > 1}

        violations = {
            name: count
            for name, count in retry_counts.items()
            if count > self.max_retries
        }

        if not retry_counts:
            self.score = 1.0
            self.reason = "No repeated tool calls detected"
        elif not violations:
            self.score = 1.0
            max_name = max(retry_counts, key=lambda k: retry_counts[k])
            self.reason = f"Repeated tools within bounds (max: {max_name}={retry_counts[max_name]}, limit: {self.max_retries})"
        else:
            self.score = 0.0
            self.reason = (
                f"Retry limit exceeded: {violations} (limit: {self.max_retries})"
            )

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Bounded Troubleshooting"

    def is_successful(self) -> bool:
        return self.success is True
