"""Brief Source Faithfulness metric (M-SM-7)."""

from typing import ClassVar

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from ._base import MetisTurnMetric, mark_skipped
from ._extraction import extract_brief, extract_source_texts
from ._judge import _get_judge_model


class BriefSourceFaithfulnessMetric(MetisTurnMetric):
    """All brief claims traceable to sources? (M-SM-7)

    Extract-and-judge. Treats the extracted brief as the claim set and the
    source documents as the grounding context, then scores faithfulness with
    DeepEval's built-in FaithfulnessMetric. Skips when either the brief or the
    source material is unavailable.
    """

    tags: ClassVar[tuple[str, ...]] = ("presentation", "per-turn", "judge-graded")
    async_mode = False

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = FaithfulnessMetric(
                threshold=self.threshold,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        brief = extract_brief(test_case)
        sources = extract_source_texts(test_case)

        if not brief or not sources:
            return mark_skipped(
                self,
                "brief or source material unavailable; brief source "
                "faithfulness cannot be assessed.",
            )

        faith_tc = LLMTestCase(
            input=test_case.input,
            actual_output=brief,
            retrieval_context=["\n\n---\n\n".join(sources)],
            metadata=test_case.metadata,
        )
        metric = self._get_metric()
        metric.measure(faith_tc)
        self.score = metric.score
        self.evaluation_cost = getattr(metric, "evaluation_cost", None)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Brief Source Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
