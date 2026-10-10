"""Cross-Agent Context Retention grader (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnGrader, mark_skipped
from ._types import LlmTestCaseMetadata, OrcaChatMetadata


class CrossAgentContextRetentionGrader(MetisTurnGrader):
    """Context preserved across subagent invocations?

    Code grader: checks that multi-turn conversations maintain context
    by looking at whether spoke_context carries over and is not
    redundantly re-asked.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "code-graded",
    )

    async_mode = False

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata)
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )
        spoke_context = metadata.get("spoke_context") or {}
        clarifications = metadata.get("clarification_requests", [])

        num_history = chat_meta.num_history_messages

        if num_history == 0:
            return mark_skipped(
                self, "First message in session (no prior context to retain)"
            )

        if spoke_context:
            cached_values = set(str(v).lower() for v in spoke_context.values() if v)
            redundant = 0
            for c in clarifications:
                q_text = str(c.output or c.input or "").lower()
                for val in cached_values:
                    if val and len(val) > 3 and val in q_text:
                        redundant += 1
                        break

            if redundant > 0:
                self.score = 0.0
                self.reason = f"{redundant} re-ask(s) for info already in spoke_context from prior turn"
            else:
                self.score = 1.0
                self.reason = f"Context retained across turns (spoke_context has {len(spoke_context)} keys, no re-asks)"
        else:
            self.score = 1.0
            self.reason = f"Multi-turn conversation (history={num_history}), no spoke_context but no redundant asks"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Cross-Agent Context Retention"

    def is_successful(self) -> bool:
        return self.success is True
