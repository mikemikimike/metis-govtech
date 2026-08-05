"""Direct Handle Recognition metric (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import TraceMetadata


class DirectHandleRecognitionMetric(SyncBaseMetric):
    """Handles directly when no subagent fits?

    For queries annotated as direct-handle (expected_subagent=None),
    asserts that no delegation event occurred in the trace.
    Without annotations, skips.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "code-graded",
        "annotation-dependent",
    )

    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        annotations = metadata.get("annotations", {})

        if "expected_subagent" not in annotations:
            self.score = 1.0
            self.skipped = True
            self.reason = "No expected_subagent annotated — SKIPPED"
            self.success = True
            return self.score or 0.0

        expected = annotations["expected_subagent"]

        if expected is not None:
            self.score = 1.0
            self.skipped = True
            self.reason = "Not a direct-handle case — SKIPPED"
            self.success = True
            return self.score or 0.0

        delegation = metadata.get("delegation")

        if delegation is None:
            self.score = 1.0
            self.reason = "Correctly handled directly without delegation"
        else:
            self.score = 0.0
            self.reason = f"Should have handled directly but delegated to '{delegation.get('target', '?')}'"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Direct Handle Recognition"

    def is_successful(self) -> bool:
        return self.success is True
