"""Chart Technical Correctness metric (M-DA-10)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model
from ._types import TraceMetadata


def _extract_chart_evidence(test_case: LLMTestCase) -> dict | None:
    """Collect chart type/granularity/format facts from observations."""
    metadata = cast(TraceMetadata, test_case.metadata)
    observations = metadata.get("observations") or []
    evidence: dict = {}
    for obs in observations:
        obs_meta = obs.get("metadata") or {}
        chart_meta = obs_meta.get("chart_metadata") or {}
        for key in ("type", "num_categories", "num_data_points", "output_format"):
            if key in chart_meta and key not in evidence:
                evidence[key] = chart_meta[key]
        output = obs.get("output")
        if isinstance(output, dict):
            if "chart_type" in output:
                evidence.setdefault("type", output["chart_type"])
            if "categories" in output:
                evidence.setdefault(
                    "num_categories", len(output.get("categories") or [])
                )
            if "data_points" in output:
                evidence.setdefault("num_data_points", output.get("data_points"))
            file_name = output.get("file")
            if isinstance(file_name, str) and "." in file_name:
                evidence.setdefault("output_format", file_name.rsplit(".", 1)[1])
    annotations = metadata.get("annotations") or {}
    if annotations.get("data_pattern"):
        evidence["data_pattern"] = annotations["data_pattern"]
    if annotations.get("expected_format"):
        evidence["expected_format"] = annotations["expected_format"]
    return evidence or None


class ChartTechnicalCorrectnessMetric(MetisTurnMetric):
    """Is the chart technically correct across four dimensions? (M-DA-10)

    Canonical judge for M-DA-10. Evaluates chart type fit, granularity
    (<=12 categories, >=3 points), outlier handling, and output format in one
    result and explains all four. Skips when no chart is observable. The
    narrow helpers (ChartTypeFitness, ChartGranularity, OutlierHandlingQuality,
    ChartFormatCompliance) remain available for single-dimension use.
    """

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Chart Technical Correctness",
                model=_get_judge_model(),
                criteria=(
                    "The chart type matches the data pattern, granularity is "
                    "appropriate (<=12 categories, >=3 data points), outliers "
                    "are handled sensibly, and the output format is correct; "
                    "judge these four technical dimensions together over the "
                    "extracted chart facts and the agent's response.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the extracted chart facts; the 'actual_output' is the "
                    "agent's description of the chart.\n\n"
                    "Assess all four dimensions and explain each:\n"
                    "1. Type fit: Does the chart type match the data pattern "
                    "(e.g. line for time series, bar for ranking, scatter for "
                    "correlation)?\n"
                    "2. Granularity: Is it neither too crowded (>12 "
                    "categories) nor too sparse (<3 data points)?\n"
                    "3. Outliers: Are outliers handled sensibly (not silently "
                    "distorting the view; excluded only with a note)?\n"
                    "4. Output format: Is the saved format correct for the "
                    "request (e.g. not a .txt where an image was asked)?\n\n"
                    "Score 1.0 when all four dimensions are satisfied. "
                    "Score 0.5 when one dimension is weak. "
                    "Score 0.0 when two or more dimensions fail." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase, evidence: dict) -> LLMTestCase:
        lines = [f"{k}: {v}" for k, v in evidence.items()]
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=["Chart facts:\n" + "\n".join(lines)],
            metadata=test_case.metadata,
        )

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        evidence = _extract_chart_evidence(test_case)
        if evidence is None:
            return mark_skipped(
                self,
                "no chart observed; technical correctness is not applicable.",
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, evidence))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Chart Technical Correctness"

    def is_successful(self) -> bool:
        return self.success is True
