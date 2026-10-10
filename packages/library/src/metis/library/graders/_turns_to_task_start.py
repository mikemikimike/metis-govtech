"""M-UNI-2: Turns to Task Start grader."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnGrader
from ._types import LlmTestCaseMetadata, OrcaChatMetadata


class TurnsToTaskStartGrader(MetisTurnGrader):
    """How many turns before work begins?

    Uses the num_history_messages from orca-chat span and counts
    request_user_input calls. Each request_user_input is a round-trip
    back to the user before work starts. Gate: <=2 turns.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "code-graded")
    async_mode = False

    def __init__(self, threshold: float = 1.0, max_turns: int = 2) -> None:
        self.threshold = threshold
        self.max_turns = max_turns
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata)
        clarifications = metadata.get("clarification_requests", [])
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )

        # Each request_user_input is a turn back to the user
        turns_before_action = len(clarifications)
        num_history = chat_meta.num_history_messages

        self.score = 1.0 if turns_before_action <= self.max_turns else 0.0
        self.reason = (
            f"{turns_before_action} clarification "
            f"round-trip(s) before task execution "
            f"(max: {self.max_turns}, "
            f"history_msgs: {num_history})"
        )
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Turns to Task Start"

    def is_successful(self) -> bool:
        return self.success is True
