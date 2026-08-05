"""Chart Granularity metric (M-DA-11)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import TraceMetadata


class ChartGranularityMetric(SyncBaseMetric):
    """Chart not too crowded (<=12 categories) nor too sparse (>=3 points)?

    Parses chart metadata from trace observations.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
        "per-turn",
        "code-graded",
        "condition-gated",
    )
    async_mode = False

    def __init__(
        self,
        threshold: float = 1.0,
        max_categories: int = 12,
        min_data_points: int = 3,
    ):
        self.threshold = threshold
        self.max_categories = max_categories
        self.min_data_points = min_data_points
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        observations = metadata.get("observations", [])
        chart_meta = self._extract_chart_metadata(observations)

        if chart_meta is None:
            self.score = 1.0
            self.skipped = True
            self.reason = "No chart generated in this trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        num_categories = chart_meta.get("num_categories", 0)
        num_data_points = chart_meta.get("num_data_points", 0)

        too_crowded = num_categories > self.max_categories
        too_sparse = num_data_points < self.min_data_points

        if not too_crowded and not too_sparse:
            self.score = 1.0
            self.reason = (
                f"Chart granularity OK: {num_categories} categories "
                f"(max {self.max_categories}), {num_data_points} data points "
                f"(min {self.min_data_points})"
            )
        else:
            self.score = 0.0
            issues = []
            if too_crowded:
                issues.append(
                    f"too crowded ({num_categories} categories > {self.max_categories})"
                )
            if too_sparse:
                issues.append(
                    f"too sparse ({num_data_points} data points < {self.min_data_points})"
                )
            self.reason = f"Chart granularity FAIL: {', '.join(issues)}"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    def _extract_chart_metadata(self, observations: list) -> dict | None:
        for obs in observations:
            obs_meta = obs.get("metadata") or {}
            if "chart_metadata" in obs_meta:
                return obs_meta["chart_metadata"]
            output = obs.get("output")
            if isinstance(output, dict) and "chart_type" in output:
                return {
                    "num_categories": len(output.get("categories", [])),
                    "num_data_points": output.get("data_points", 0),
                    "type": output.get("chart_type"),
                }
        return None

    @property
    def __name__(self) -> str:
        return "Chart Granularity"

    def is_successful(self) -> bool:
        return self.success is True
