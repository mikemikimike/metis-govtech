"""Outlier Handling Quality metric (M-DA-19)."""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model

if TYPE_CHECKING:
    from ._types import LlmTestCaseMetadata


def _has_chart_observations(test_case: LLMTestCase) -> bool:
    """Check if the trace has actual chart generation observations."""
    metadata = cast("LlmTestCaseMetadata", test_case.metadata)
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


class OutlierHandlingQualityMetric(MetisTurnMetric):
    """Outliers handled sensibly in charts?

    Skips when no chart content is present in the output.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "analysis",
        "per-turn",
        "judge-graded",
    )

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
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

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        if not _has_chart_observations(test_case):
            return mark_skipped(self, "No chart content in output")

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Outlier Handling Quality"

    def is_successful(self) -> bool:
        return self.success is True
