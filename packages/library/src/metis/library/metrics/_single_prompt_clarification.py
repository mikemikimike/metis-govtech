"""M-UNI-1: Single-Prompt Clarification metric."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnMetric
from ._types import TraceMetadata


class SinglePromptClarificationMetric(MetisTurnMetric):
    """All clarifications should be asked in a single message.

    Uses request_user_input TOOL observations from the span tree.
    If the agent asks for user input more than once, that's multiple
    clarification rounds — it should batch them into one form/message.
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
        clarifications = metadata.get("clarification_requests", [])

        clarification_count = len(clarifications)

        if clarification_count == 0:
            self.score = 1.0
            self.reason = "No clarification requests (proceeded directly)"
            self.success = True
            return self.score or 0.0

        self.score = 1.0 if clarification_count <= 1 else 0.0
        status = (
            "OK, single prompt"
            if clarification_count <= 1
            else "FAIL: should batch into one"
        )
        self.reason = f"{clarification_count} request_user_input call(s) — {status}"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Single-Prompt Clarification"

    def is_successful(self) -> bool:
        return self.success is True
