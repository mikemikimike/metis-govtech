"""Outlier Handling Quality metric (M-DA-19)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
from ._judge import _get_judge_model
from ._types import TraceMetadata


def _has_chart_observations(test_case: LLMTestCase) -> bool:
    """Check if the trace has actual chart generation observations."""
    metadata = cast(TraceMetadata, test_case.metadata)
    observations = metadata.get("observations", [])
    for obs in observations:
        obs_meta = obs.get("metadata") or {}
        if "chart_metadata" in obs_meta:
            return True
        output = obs.get("output")
        if isinstance(output, dict):
            if "chart_type" in output:
                return True
            filename = output.get("file", "")
            if any(filename.endswith(ext) for ext in [".png", ".svg", ".vl.json"]):
                return True
    return False


class OutlierHandlingQualityMetric(SyncBaseMetric):
    """Outliers handled sensibly in charts?

    Skips when no chart content is present in the output.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
        "per-turn",
        "judge-graded",
    )

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Outlier Handling Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate how the agent handles outliers in "
                    "its charts/visualizations.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' describes the analysis and "
                    "charts generated.\n\n"
                    "Check:\n"
                    "1. If outliers are present, do they distort "
                    "the visualization for the majority?\n"
                    "2. If outliers were excluded, is this mentioned "
                    "explicitly?\n"
                    "3. Is the handling sensible? (e.g. log scale, "
                    "separate annotation, axis break)\n\n"
                    "Score 1.0 if outliers handled well (or no "
                    "outliers present). "
                    "Score 0.5 if outliers are acknowledged but "
                    "handling is suboptimal. "
                    "Score 0.0 if outliers distort the chart badly, "
                    "or are silently excluded." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _has_chart_observations(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No chart content in output — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self._absorb_geval_cost(geval)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        if not _has_chart_observations(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No chart content in output — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self._absorb_geval_cost(geval)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Outlier Handling Quality"

    def is_successful(self) -> bool:
        return self.success is True
