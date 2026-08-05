"""M-UNI-4: Context Reuse metric."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import TraceMetadata


class ContextReuseMetric(SyncBaseMetric):
    """Uses cached context instead of re-asking?

    Detects request_user_input calls that ask for information already present
    in spoke_context. Passes if no redundant re-asks are found.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "code-graded")
    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        observations = metadata.get("observations", [])
        spoke_context = metadata.get("spoke_context") or {}

        if not spoke_context:
            self.score = 1.0
            self.skipped = True
            self.reason = "No spoke_context present (first interaction) — SKIPPED"
            self.success = True
            return self.score or 0.0

        cached_keys = set(spoke_context.keys())
        redundant_asks = 0

        for obs in observations:
            if obs.get("name") == "request_user_input":
                output = obs.get("output") or {}
                question_text = str(output).lower()
                for key in cached_keys:
                    if key.lower() in question_text:
                        redundant_asks += 1
                        break

        self.score = 1.0 if redundant_asks == 0 else 0.0
        self.reason = f"{redundant_asks} redundant re-ask(s) for info already in spoke_context (cached keys: {list(cached_keys)})"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Context Reuse"

    def is_successful(self) -> bool:
        return self.success is True
