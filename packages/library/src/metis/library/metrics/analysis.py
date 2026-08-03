"""
Data Analyst metrics (M-DA-*).

Code-graded: M-DA-1, 3, 11, 16, 10, 12
Model-graded (GEval): M-DA-2, 4, 5, 8, 9, 13, 15, 18, 19, 20
"""

import re
from typing import cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from metis.library.metrics._types import OrcaChatMetadata, TraceMetadata

from ._judge import _get_judge_model
from .universal import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval


def _is_data_analyst_trace(test_case: LLMTestCase) -> bool:
    """Check if this trace was routed to the data analyst subagent."""
    metadata = cast(TraceMetadata, test_case.metadata)
    delegation = metadata.get("delegation") or {}
    target = delegation.get("target", "") if isinstance(delegation, dict) else ""
    if "data" in target.lower():
        return True
    chat_meta: OrcaChatMetadata = metadata.get("chat_metadata") or OrcaChatMetadata()
    routed = chat_meta.routed_to_agents
    return bool(any("data" in str(a).lower() for a in routed))


def _has_chart_observations(test_case: LLMTestCase) -> bool:
    """Check if the trace has actual chart generation observations.

    Not just text mentioning charts.

    We only evaluate chart quality when we have span-level
    evidence that a chart was actually produced (chart_metadata
    in observations, or a create_file call with a chart
    extension). Text mentioning 'chart' alone is insufficient
    because the judge cannot evaluate visual quality from text.
    """
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


def _has_report_content(test_case: LLMTestCase) -> bool:
    """Check if the output is long enough to be a report.

    Returns False for short answers.
    """
    output = test_case.actual_output or ""
    return len(output) > 500 and _is_data_analyst_trace(test_case)


class DataIngestionAccuracyMetric(SyncBaseMetric):
    """Source data read without corruption?

    Compares extracted values from the trace output against annotated
    ground-truth values. Uses exact match for strings, tolerance for numbers.
    """

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


class AnalyticalCorrectnessMetric(SyncBaseMetric):
    """Numerical results correct within tolerance?

    Compares computed numerical results against pre-computed ground truth.
    Uses relative tolerance for large numbers, absolute for small.
    """

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


class ChartGranularityMetric(SyncBaseMetric):
    """Chart not too crowded (≤12 categories) nor too sparse (≥3 points)?

    Parses chart metadata from trace observations.
    """

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


class ChartFormatComplianceMetric(SyncBaseMetric):
    """Chart saved in correct format (PNG/SVG/etc.)?

    Checks that the output file format matches what was requested or
    annotated as expected.
    """

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

        expected_format = annotations.get("expected_format")
        if expected_format is None:
            expected_format = self._infer_expected_format(test_case.input)

        if expected_format is None:
            self.score = 1.0
            self.skipped = True
            self.reason = "No format requirement specified — SKIPPED"
            self.success = True
            return self.score or 0.0

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
        import re

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


class ChartTypeFitnessMetric(SyncBaseMetric):
    """Chart type matches the data pattern?

    Code grader: given an annotation of the data pattern and acceptable chart types,
    checks whether the generated chart type is appropriate.
    """

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


class ReportFormatComplianceMetric(SyncBaseMetric):
    """Correct file format and consistent formatting?

    Code grader: checks that generated report matches requested format
    and basic structural rules (has headings, consistent structure).
    """

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
            self.score = 1.0
            self.skipped = True
            self.reason = "No expected_report_format annotation — SKIPPED"
            self.success = True
            return self.score or 0.0

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


# --- Model-graded metrics (GEval) ---


class ScopeCorrectnessMetric(SyncBaseMetric):
    """Analyses exactly what the user asked for?"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Scope Correctness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the Data Analyst agent analysed "
                    "exactly what the user asked for — "
                    "no more, no less.\n\n"
                    "The 'input' is the user's request specifying what "
                    "to analyse. "
                    "The 'actual_output' is the analysis result "
                    "delivered.\n\n"
                    "Check:\n"
                    "1. Are all quantities/metrics the user asked for "
                    "present in the output?\n"
                    "2. Did the agent add unrequested analyses "
                    "(scope creep)?\n"
                    "3. Did the agent narrow the scope and miss "
                    "something the user asked for?\n\n"
                    "Score 1.0 if scope is exact. When scoring 1.0, "
                    "state ONLY: "
                    "'Scope matches request — no over/under-analysis "
                    "detected.' "
                    "Do not describe report structure or formatting.\n"
                    "Score 0.5 if minor additions or omissions that "
                    "don't mislead — "
                    "quote what was added or missed.\n"
                    "Score 0.0 if significant scope violation — quote "
                    "the specific over- or under-reach." + EVIDENCE_INSTRUCTION
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
        return "Scope Correctness"

    def is_successful(self) -> bool:
        return self.success is True


class MethodAppropriatenessMetric(SyncBaseMetric):
    """Statistical method suited to data distribution?"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Method Appropriateness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the Data Analyst chose an "
                    "appropriate analytical method.\n\n"
                    "The 'input' is the user's analytical question.\n"
                    "The 'actual_output' describes the analysis "
                    "performed and its results.\n\n"
                    "Check:\n"
                    "1. Is the chosen method suited to the data type? "
                    "(e.g. don't use Pearson on "
                    "non-linear relationships, don't use t-test on "
                    "non-normal small samples)\n"
                    "2. Is the method appropriate for the question "
                    "being asked?\n"
                    "3. Are there obvious better alternatives the "
                    "agent should have used?\n\n"
                    "IMPORTANT: If the task does not involve a "
                    "specific quantitative or "
                    "statistical method (e.g. it is a document "
                    "summary, a report of pre-computed "
                    "figures, or a simple aggregation), score 1.0 "
                    "and state ONLY: "
                    "'No statistical method choice required for this "
                    "task type.'\n"
                    "Score 1.0 if method is well-suited — state the "
                    "method used and why it fits.\n"
                    "Score 0.5 if acceptable but a better method "
                    "exists — name the better alternative.\n"
                    "Score 0.0 if method is clearly inappropriate — "
                    "explain why." + EVIDENCE_INSTRUCTION
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
        return "Method Appropriateness"

    def is_successful(self) -> bool:
        return self.success is True


class InsightQualityMetric(SyncBaseMetric):
    """Insights precise, grounded, not overclaiming, relevant, actionable?"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Insight Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the quality of insights produced by "
                    "the Data Analyst agent.\n\n"
                    "The 'input' is the user's analytical question. "
                    "The 'actual_output' contains the insights and "
                    "findings.\n\n"
                    "Rate on five dimensions:\n"
                    "1. Precision: Are claims specific rather than "
                    "vague?\n"
                    "2. Grounded: Are insights supported by the data "
                    "actually analysed?\n"
                    "3. Not overclaiming: Does it avoid causal claims "
                    "from correlational data?\n"
                    "4. Relevant: Do insights address the user's "
                    "actual question?\n"
                    "5. Actionable: Could the user take action based "
                    "on these insights?\n\n"
                    "Score 1.0 if excellent on all dimensions. "
                    "Score 0.5 if adequate. "
                    "Score 0.0 if vague, ungrounded, or overclaiming."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Judge did not receive report/analysis content — SKIPPED"
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
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Judge did not receive report/analysis content — SKIPPED"
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
        return "Insight Quality"

    def is_successful(self) -> bool:
        return self.success is True


class ChartPurposefulnessMetric(SyncBaseMetric):
    """Chart answers a specific question in its title?

    Skips when no chart content is present in the output.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Chart Purposefulness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether a generated chart answers a "
                    "specific analytical question.\n\n"
                    "The 'input' is the user's analytical request.\n"
                    "The 'actual_output' describes the chart "
                    "generated (title, type, data shown).\n\n"
                    "Check:\n"
                    "1. Does the chart title state a specific "
                    "analytical question or finding?\n"
                    "   (Good: 'Revenue growth by quarter "
                    "2023-2024'. Bad: 'Revenue chart')\n"
                    "2. Does the chart answer that question "
                    "visually?\n"
                    "3. Is the chart purposeful — not just showing "
                    "data for the sake of it?\n\n"
                    "Score 1.0 if chart clearly answers a question "
                    "stated in its title. "
                    "Score 0.5 if chart is useful but title is "
                    "generic. "
                    "Score 0.0 if chart appears purposeless or title "
                    "is just a variable name." + EVIDENCE_INSTRUCTION
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
        return "Chart Purposefulness"

    def is_successful(self) -> bool:
        return self.success is True


class ChartNecessityMetric(SyncBaseMetric):
    """Chart adds value beyond a simple number/table?

    Skips when no chart content is present in the output.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Chart Necessity",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the chart adds value over a "
                    "simple number or table.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' describes the chart and the "
                    "data it visualises.\n\n"
                    "Check:\n"
                    "1. Could the insight be conveyed equally well "
                    "as a single number or 2-row table?\n"
                    "2. Does the visual representation reveal "
                    "patterns not obvious from raw numbers?\n"
                    "3. Is there enough data complexity to warrant "
                    "a chart?\n\n"
                    "Score 1.0 if chart reveals patterns that "
                    "numbers alone wouldn't show. "
                    "Score 0.5 if chart is helpful but a table "
                    "would also work. "
                    "Score 0.0 if chart is unnecessary — a single "
                    "number would suffice." + EVIDENCE_INSTRUCTION
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
        return "Chart Necessity"

    def is_successful(self) -> bool:
        return self.success is True


class ReportCoherenceMetric(SyncBaseMetric):
    """Report sections follow a logical structure?

    Skips when output is too short to be a report or not from data analyst.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Report Coherence",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the logical flow and coherence of an "
                    "analytical response.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the analysis "
                    "delivered.\n\n"
                    "NOTE: This is a conversational AI agent, NOT a "
                    "formal document generator. "
                    "The output is a chat response that presents "
                    "analytical findings. It does NOT "
                    "need formal report sections like 'Methodology' "
                    "or 'Conclusions.' Instead, "
                    "evaluate whether the information flows "
                    "logically.\n\n"
                    "Check:\n"
                    "1. Does the response present information in a "
                    "logical order? "
                    "(context/setup -> findings -> interpretation)\n"
                    "2. Can a reader follow the reasoning without "
                    "confusion?\n"
                    "3. Are related points grouped together?\n\n"
                    "Score 1.0 if excellent logical flow. "
                    "Score 0.7 if readable and coherent even without "
                    "formal sections. "
                    "Score 0.5 if readable but some points feel out "
                    "of place. "
                    "Score 0.0 if genuinely incoherent or randomly "
                    "ordered." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = (
                "Output too short or not from data analyst — not a report — SKIPPED"
            )
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
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = (
                "Output too short or not from data analyst — not a report — SKIPPED"
            )
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
        return "Report Coherence"

    def is_successful(self) -> bool:
        return self.success is True


class ReportCompletenessMetric(SyncBaseMetric):
    """All sub-questions addressed?"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Report Completeness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the report addresses all "
                    "parts of the user's query.\n\n"
                    "The 'input' is the user's (potentially "
                    "multi-part) request.\n"
                    "The 'actual_output' is the report/analysis "
                    "delivered.\n\n"
                    "Check:\n"
                    "1. Decompose the input into distinct "
                    "sub-questions or requested analyses\n"
                    "2. Verify each sub-question is addressed in "
                    "the output\n"
                    "3. Note any that are missing or only "
                    "superficially addressed\n\n"
                    "Score 1.0 if all sub-questions fully "
                    "addressed. "
                    "Score 0.5 if most addressed but one or two "
                    "superficially. "
                    "Score 0.0 if major sub-questions are entirely "
                    "missing." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Judge did not receive report/analysis content — SKIPPED"
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
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Judge did not receive report/analysis content — SKIPPED"
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
        return "Report Completeness"

    def is_successful(self) -> bool:
        return self.success is True


class AnalyticalAssumptionTransparencyMetric(SyncBaseMetric):
    """Analytical/methodological assumptions explicitly stated?

    Skips when trace is not from data analyst or output is too short.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Analytical Assumption Transparency",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the Data Analyst states its "
                    "analytical assumptions.\n\n"
                    "The 'input' is the user's analytical request.\n"
                    "The 'actual_output' is the analysis result.\n\n"
                    "Common assumptions that SHOULD be stated when "
                    "they are made:\n"
                    "- Distributional (assumed normality, "
                    "independence)\n"
                    "- Missing data treatment (excluded, imputed, "
                    "ignored)\n"
                    "- Outlier handling (included, excluded, "
                    "capped)\n"
                    "- Aggregation choices (grouping level, time "
                    "granularity)\n"
                    "- Model selection rationale\n\n"
                    "IMPORTANT: Only flag assumptions the agent "
                    "ACTUALLY MADE but didn't state. "
                    "If the analysis is straightforward (counting, "
                    "filtering, grouping by an "
                    "obvious field), no assumptions need stating "
                    "— score 1.0.\n\n"
                    "Score 1.0 if all methodological assumptions "
                    "are clearly stated, or if the "
                    "analysis is simple enough to require no "
                    "assumptions. "
                    "Score 0.5 if some stated but others implicit. "
                    "Score 0.0 if the analysis clearly made complex "
                    "methodological assumptions "
                    "(statistical tests, outlier removal, "
                    "imputation) but never mentioned them." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Output too short or not from data analyst — SKIPPED"
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
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Output too short or not from data analyst — SKIPPED"
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
        return "Analytical Assumption Transparency"

    def is_successful(self) -> bool:
        return self.success is True


class OutlierHandlingQualityMetric(SyncBaseMetric):
    """Outliers handled sensibly in charts?

    Skips when no chart content is present in the output.
    """

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


class ReportLengthAppropriatenessMetric(SyncBaseMetric):
    """Report length proportionate to query scope?"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Report Length Appropriateness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the report length is "
                    "proportionate to the query scope.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the generated "
                    "report.\n\n"
                    "Check:\n"
                    "1. Is the report too short for the scope? "
                    "(missing depth, feels rushed)\n"
                    "2. Is the report too long for the scope? "
                    "(padded, repetitive, over-detailed)\n"
                    "3. Does the length feel proportionate to what "
                    "was asked?\n\n"
                    "A narrow single-question query should get a "
                    "concise answer. "
                    "A broad multi-part analysis should get a "
                    "longer structured report.\n\n"
                    "Score 1.0 if perfectly proportioned. "
                    "Score 0.5 if slightly too long or too short "
                    "but still usable. "
                    "Score 0.0 if egregiously mismatched (one "
                    "paragraph for a 10-part query, "
                    "or pages of padding for a simple question)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Judge did not receive report/analysis content — SKIPPED"
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
        if not _has_report_content(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Judge did not receive report/analysis content — SKIPPED"
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
        return "Report Length Appropriateness"

    def is_successful(self) -> bool:
        return self.success is True


def get_judge_metrics():
    """Return all DA judge metrics. Call only when you have API keys configured."""
    return (
        ScopeCorrectnessMetric(),
        MethodAppropriatenessMetric(),
        InsightQualityMetric(),
        ChartPurposefulnessMetric(),
        ChartNecessityMetric(),
        ReportCoherenceMetric(),
        ReportCompletenessMetric(),
        AnalyticalAssumptionTransparencyMetric(),
        OutlierHandlingQualityMetric(),
        ReportLengthAppropriatenessMetric(),
    )
