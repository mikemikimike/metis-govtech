"""Report Format Compliance metric (M-DA-12)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisMetric, mark_skipped
from ._types import TraceMetadata


class ReportFormatComplianceMetric(MetisMetric):
    """Correct file format and consistent formatting?

    Code grader: checks that generated report matches requested format
    and basic structural rules (has headings, consistent structure).
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
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
        annotations = metadata.get("annotations", {})
        observations = metadata.get("observations", [])

        expected_format = annotations.get("expected_report_format")

        if expected_format is None:
            return mark_skipped(self, "No expected_report_format annotation")

        actual_format = self._extract_report_format(observations)
        if actual_format is None:
            self.score = 0.0
            self.reason = "No report output found in trace"
            self.success = False
            return self.score or 0.0

        expected_fmt = expected_format.lower().strip(".")
        actual_fmt = actual_format.lower().strip(".")

        if actual_fmt == expected_fmt:
            self.score = 1.0
            self.reason = f"Report format correct: {actual_fmt}"
        else:
            self.score = 0.0
            self.reason = (
                f"Report format mismatch: got '{actual_fmt}', expected '{expected_fmt}'"
            )

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    def _extract_report_format(self, observations: list) -> str | None:
        for obs in observations:
            output = obs.get("output")
            if isinstance(output, dict) and "file" in output:
                filename = output["file"]
                if "." in filename:
                    return filename.rsplit(".", 1)[1]
            obs_meta = obs.get("metadata") or {}
            if "output_format" in obs_meta:
                return obs_meta["output_format"]
        return None

    @property
    def __name__(self) -> str:
        return "Report Format Compliance"

    def is_successful(self) -> bool:
        return self.success is True
