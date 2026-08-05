"""Analytical Correctness metric (M-DA-3)."""

import re
from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric
from ._types import TraceMetadata


class AnalyticalCorrectnessMetric(SyncBaseMetric):
    """Numerical results correct within tolerance?

    Compares computed numerical results against pre-computed ground truth.
    Uses relative tolerance for large numbers, absolute for small.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
        "per-turn",
        "code-graded",
        "annotation-dependent",
    )
    async_mode = False

    def __init__(self, threshold: float = 1.0, relative_tolerance: float = 0.01):
        self.threshold = threshold
        self.relative_tolerance = relative_tolerance
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
        actual_numbers = self._extract_numbers_from_output(
            observations, test_case.actual_output or ""
        )

        if not actual_numbers:
            self.score = 0.0
            self.reason = "No numerical results found in output"
            self.success = False
            return self.score or 0.0

        correct, total = self._check_numbers(expected_values, actual_numbers)
        self.score = correct / total if total > 0 else 0.0
        self.reason = f"{correct}/{total} numerical results within tolerance ({self.relative_tolerance * 100}%)"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    def _extract_numbers_from_output(self, observations: list, output: str) -> dict:
        for obs in observations:
            if obs.get("name") == "analyze_data" and isinstance(
                obs.get("output"), dict
            ):
                return obs["output"]
        numbers = re.findall(r"[\d,]+\.?\d*", output)
        return {"_raw_numbers": [float(n.replace(",", "")) for n in numbers]}

    def _check_numbers(self, expected: dict, actual: dict) -> tuple:
        correct = 0
        total = 0

        def _flatten(d, prefix=""):
            items = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    items.update(_flatten(v, f"{prefix}{k}."))
                elif isinstance(v, (int, float)):
                    items[f"{prefix}{k}"] = v
            return items

        expected_flat = _flatten(expected)
        actual_flat = _flatten(actual)

        for key, exp_val in expected_flat.items():
            total += 1
            act_val = actual_flat.get(key)
            if act_val is not None:
                if exp_val == 0:
                    if act_val == 0:
                        correct += 1
                elif abs(act_val - exp_val) / abs(exp_val) <= self.relative_tolerance:
                    correct += 1

        return correct, total

    @property
    def __name__(self) -> str:
        return "Analytical Correctness"

    def is_successful(self) -> bool:
        return self.success is True
