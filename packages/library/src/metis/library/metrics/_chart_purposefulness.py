"""Chart Purposefulness metric (M-DA-8)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisMetric, _ContextAwareGEval, mark_skipped
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


class ChartPurposefulnessMetric(MetisMetric):
    """Chart answers a specific question in its title?

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

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
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
        return "Chart Purposefulness"

    def is_successful(self) -> bool:
        return self.success is True
