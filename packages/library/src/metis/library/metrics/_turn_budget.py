"""M-UNI-12: Turn Budget metric."""

from typing import TYPE_CHECKING, ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnMetric, mark_skipped

if TYPE_CHECKING:
    from ._types import LlmTestCaseMetadata


class TurnBudgetMetric(MetisTurnMetric):
    """Session completed within the allowed turn budget.

    Checks that the total number of conversation turns did not exceed
    max_turns. Passes if turns <= max_turns, fails otherwise.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "code-graded")
    async_mode = False

    def __init__(self, threshold: float = 1.0, max_turns: int = 10) -> None:
        self.threshold = threshold
        self.max_turns = max_turns
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata or {})
        total_turns = metadata.get("total_turns")
        if total_turns is None:
            return mark_skipped(self, "total_turns not present in metadata")

        self.score = 1.0 if total_turns <= self.max_turns else 0.0
        self.reason = f"Session used {total_turns} turn(s) (budget: {self.max_turns})"
        self.success = self.score >= self.threshold
        return self.score

    @property
    def __name__(self) -> str:
        return "Turn Budget"

    def is_successful(self) -> bool:
        return self.success
