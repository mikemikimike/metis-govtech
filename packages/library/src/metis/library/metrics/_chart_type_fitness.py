"""Chart Type Fitness metric (M-DA-10)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import TraceMetadata


class ChartTypeFitnessMetric(SyncBaseMetric):
    """Chart type matches the data pattern?

    Code grader: given an annotation of the data pattern and acceptable chart types,
    checks whether the generated chart type is appropriate.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
        "per-turn",
        "code-graded",
    )

    PATTERN_ACCEPTABLE_TYPES = {
        "time_series": {"line", "area", "bar"},
        "part_of_whole": {"pie", "donut", "stacked_bar", "treemap"},
        "ranking": {"bar", "horizontal_bar", "lollipop"},
        "distribution": {"histogram", "box", "violin", "density"},
        "correlation": {"scatter", "bubble", "heatmap"},
        "composition": {"stacked_bar", "stacked_area", "waterfall"},
    }

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        annotations = metadata.get("annotations", {})
        observations = metadata.get("observations", [])

        data_pattern = annotations.get("data_pattern")
        acceptable_types = annotations.get("acceptable_chart_types")

        if not acceptable_types and data_pattern:
            acceptable_types = list(self.PATTERN_ACCEPTABLE_TYPES.get(data_pattern, []))

        if not acceptable_types:
            self.score = 1.0
            self.skipped = True
            self.reason = (
                "No data_pattern or acceptable_chart_types annotated — SKIPPED"
            )
            self.success = True
            return self.score or 0.0

        actual_type = self._extract_chart_type(observations)
        if actual_type is None:
            self.score = 0.0
            self.reason = "No chart type found in trace"
            self.success = False
            return self.score or 0.0

        actual_normalized = actual_type.lower().replace(" ", "_").replace("-", "_")
        acceptable_normalized = {
            t.lower().replace(" ", "_").replace("-", "_") for t in acceptable_types
        }

        if actual_normalized in acceptable_normalized:
            self.score = 1.0
            self.reason = f"Chart type '{actual_type}' is appropriate for pattern '{data_pattern}'"
        else:
            self.score = 0.0
            self.reason = f"Chart type '{actual_type}' not in acceptable set {acceptable_types} for pattern '{data_pattern}'"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    def _extract_chart_type(self, observations: list) -> str | None:
        for obs in observations:
            obs_meta = obs.get("metadata") or {}
            chart_meta = obs_meta.get("chart_metadata", {})
            if "type" in chart_meta:
                return chart_meta["type"]
            output = obs.get("output")
            if isinstance(output, dict) and "chart_type" in output:
                return output["chart_type"]
        return None

    @property
    def __name__(self) -> str:
        return "Chart Type Fitness"

    def is_successful(self) -> bool:
        return self.success is True
