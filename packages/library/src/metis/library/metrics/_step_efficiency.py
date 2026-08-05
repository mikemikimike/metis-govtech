"""M-UNI-3: Step Efficiency metric."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import OrcaChatMetadata, TraceMetadata


class StepEfficiencyMetric(SyncBaseMetric):
    """Task completed in near-minimum tool calls?

    Uses actual TOOL observations from the span tree. Without annotations,
    reports the count from both orca-chat metadata and observation tree
    (informational pass). With annotations, compares to expected minimum.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
        "per-turn",
        "code-graded",
        "annotation-dependent",
    )
    async_mode = False

    def __init__(self, threshold: float = 1.0, max_ratio: float = 1.3):
        self.threshold = threshold
        self.max_ratio = max_ratio
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        tool_calls = metadata.get("tool_calls", [])
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )
        annotations = metadata.get("annotations", {})

        actual_count = len(tool_calls)
        reported_count = chat_meta.num_tool_calls
        expected_minimum = annotations.get("expected_minimum_steps")

        if expected_minimum is None:
            self.score = 1.0
            self.skipped = True
            self.reason = (
                f"{actual_count} tool call(s) in "
                f"observation tree (orca-chat reports "
                f"{reported_count}), no minimum "
                f"annotated — SKIPPED"
            )
            self.success = True
            return self.score or 0.0

        if expected_minimum == 0:
            self.score = 1.0 if actual_count == 0 else 0.0
            self.reason = f"{actual_count} tool call(s), expected 0"
            self.success = (self.score or 0) >= self.threshold
            return self.score or 0.0

        ratio = actual_count / expected_minimum
        self.score = 1.0 if ratio <= self.max_ratio else 0.0
        self.reason = f"{actual_count} tool call(s) vs {expected_minimum} minimum (ratio: {ratio:.2f}, max: {self.max_ratio})"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Step Efficiency"

    def is_successful(self) -> bool:
        return self.success is True
