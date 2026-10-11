"""Chart Format Compliance grader (M-DA-16)."""

import re
from typing import TYPE_CHECKING, ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import MetisTurnGrader, mark_skipped

if TYPE_CHECKING:
    from ._types import LlmTestCaseMetadata


class ChartFormatComplianceGrader(MetisTurnGrader):
    """Chart saved in correct format (PNG/SVG/etc.)?

    Checks that the output file format matches what was requested or
    annotated as expected.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
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
        annotations = metadata.get("annotations", {})
        observations = metadata.get("observations", [])

        expected_format = annotations.get("expected_format")
        if expected_format is None:
            expected_format = self._infer_expected_format(test_case.input)

        if expected_format is None:
            return mark_skipped(self, "No format requirement specified")

        actual_format = self._extract_output_format(observations)

        if actual_format is None:
            self.score = 0.0
            self.reason = "No chart output found in trace"
            self.success = False
            return self.score or 0.0

        expected_format = expected_format.lower().strip(".")
        actual_format = actual_format.lower().strip(".")

        if actual_format == expected_format:
            self.score = 1.0
            self.reason = f"Format correct: {actual_format}"
        else:
            self.score = 0.0
            self.reason = (
                f"Format mismatch: got '{actual_format}', expected '{expected_format}'"
            )

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    def _infer_expected_format(self, user_input: str) -> str | None:
        for fmt in ["svg", "png", "jpg", "jpeg", "pdf", "html"]:
            if re.search(
                rf"\b(as|in|to|save|export|format)\b.{{0,20}}\b{fmt}\b",
                user_input.lower(),
            ):
                return fmt
        return None

    def _extract_output_format(self, observations: list) -> str | None:
        for obs in observations:
            obs_meta = obs.get("metadata") or {}
            chart_meta = obs_meta.get("chart_metadata", {})
            if "output_format" in chart_meta:
                return chart_meta["output_format"]

            output = obs.get("output")
            if isinstance(output, dict) and "file" in output:
                filename = output["file"]
                if "." in filename:
                    return filename.rsplit(".", 1)[1]
        return None

    @property
    def __name__(self) -> str:
        return "Chart Format Compliance"

    def is_successful(self) -> bool:
        return self.success is True
