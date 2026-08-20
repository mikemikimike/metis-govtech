"""Agent Status Communication metric (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnMetric, mark_skipped
from ._types import OrcaChatMetadata, TraceMetadata


class AgentStatusCommunicationMetric(MetisTurnMetric):
    """User informed which agent is handling their request?

    Code grader: checks that when delegation occurs, the output mentions
    the agent name or type being used.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "code-graded",
    )

    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")
        metadata.get("chat_metadata") or OrcaChatMetadata()

        if not delegation or not delegation["target"]:
            return mark_skipped(self, "No delegation occurred")

        target = delegation["target"]
        output_lower = (test_case.actual_output or "").lower()

        agent_names = [
            target.lower(),
            target.replace("_", " ").lower(),
            target.replace("-", " ").lower(),
        ]

        mentioned = any(name in output_lower for name in agent_names)

        if mentioned:
            self.score = 1.0
            self.reason = f"Agent '{target}' mentioned in response"
        else:
            self.score = 0.0
            self.reason = f"Agent '{target}' was used but not mentioned in the response"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Agent Status Communication"

    def is_successful(self) -> bool:
        return self.success is True
