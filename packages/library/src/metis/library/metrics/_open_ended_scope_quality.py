"""M-UNI-7: Open-Ended Scope Quality metric."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class OpenEndedScopeQualityMetric(SyncBaseMetric):
    """Agent-chosen scope appropriate when user doesn't specify?

    Full judge: evaluates whether the agent's chosen scope is comprehensive,
    relevant, and proportionate for an open-ended request.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Open-Ended Scope Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the scope the agent chose "
                    "when the user gave an open-ended "
                    "request "
                    "(e.g. 'explore this dataset', "
                    "'scan this document', "
                    "'what's interesting here').\n\n"
                    "The 'input' is the user's "
                    "open-ended request.\n"
                    "The 'actual_output' is the agent's "
                    "response showing what it chose to "
                    "cover.\n\n"
                    "Rate on three dimensions:\n"
                    "1. Comprehensive: Does it cover the "
                    "major topics/patterns a competent "
                    "analyst would?\n"
                    "2. Relevant: Is everything it "
                    "covers actually pertinent (no "
                    "filler or tangents)?\n"
                    "3. Proportionate: Is the depth "
                    "appropriate — not too shallow, not "
                    "obsessively detailed?\n\n"
                    "Score 1.0 if scope is excellent on "
                    "all dimensions. "
                    "Score 0.5 if adequate but missing a "
                    "major topic or including filler. "
                    "Score 0.0 if scope is clearly wrong "
                    "(trivial coverage of a rich "
                    "source, or "
                    "overwhelmingly irrelevant "
                    "tangents)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Open-Ended Scope Quality"

    def is_successful(self) -> bool:
        return self.success is True
