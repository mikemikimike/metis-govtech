"""Data Ingestion Accuracy metric (M-DA-1)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import TraceMetadata


class DataIngestionAccuracyMetric(SyncBaseMetric):
    """Source data read without corruption?

    Compares extracted values from the trace output against annotated
    ground-truth values. Uses exact match for strings, tolerance for numbers.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
        "per-turn",
        "code-graded",
    )
    async_mode = False

    def __init__(self, threshold: float = 1.0, numeric_tolerance: float = 0.01):
        self.threshold = threshold
        self.numeric_tolerance = numeric_tolerance
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        annotations = metadata.get("annotations", {})
        expected_values = annotations.get("expected_values")

        if expected_values is None:
            self.score = 1.0
            self.skipped = True
            self.reason = "No expected values annotated — SKIPPED"
            self.success = True
            return self.score or 0.0

        observations = metadata.get("observations", [])
        actual_output = self._extract_analysis_output(observations)

        if actual_output is None:
            self.score = 0.0
            self.reason = "No analysis output found in trace"
            self.success = False
            return self.score or 0.0

        matches, mismatches = self._compare_values(expected_values, actual_output)
        total = matches + mismatches

        self.score = matches / total if total > 0 else 0.0
        if mismatches == 0:
            self.reason = f"All {matches} value(s) match ground truth"
        else:
            self.reason = f"{matches}/{total} values correct, {mismatches} mismatch(es)"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    def _extract_analysis_output(self, observations: list) -> dict | None:
        for obs in observations:
            if obs.get("name") == "analyze_data" and obs.get("output"):
                output = obs["output"]
                if isinstance(output, dict):
                    return output
        return None

    def _compare_values(self, expected: dict, actual: dict, prefix: str = "") -> tuple:
        matches = 0
        mismatches = 0

        for key, exp_val in expected.items():
            act_val = actual.get(key)
            if act_val is None:
                mismatches += 1
                continue

            if isinstance(exp_val, dict) and isinstance(act_val, dict):
                m, mm = self._compare_values(exp_val, act_val, f"{prefix}{key}.")
                matches += m
                mismatches += mm
            elif isinstance(exp_val, (int, float)) and isinstance(
                act_val, (int, float)
            ):
                if abs(exp_val - act_val) <= abs(exp_val * self.numeric_tolerance):
                    matches += 1
                else:
                    mismatches += 1
            else:
                if str(exp_val) == str(act_val):
                    matches += 1
                else:
                    mismatches += 1

        return matches, mismatches

    @property
    def __name__(self) -> str:
        return "Data Ingestion Accuracy"

    def is_successful(self) -> bool:
        return self.success is True
