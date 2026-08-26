"""Chart Purposefulness metric (M-DA-8)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model
from ._types import LlmTestCaseMetadata


def _has_chart_observations(test_case: LLMTestCase) -> bool:
    """Check if the trace has actual chart generation observations."""
    metadata = cast(LlmTestCaseMetadata, test_case.metadata)
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


class ChartPurposefulnessMetric(MetisTurnMetric):
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
                    "Evaluate the two purposefulness dimensions of a generated "
                    "chart (M-DA-8).\n\n"
                    "The 'input' is the user's analytical request.\n"
                    "The 'actual_output' describes the chart "
                    "generated (title, type, data shown).\n\n"
                    "Assess two dimensions:\n"
                    "1. Specific question in title: Does the chart title state "
                    "a specific analytical question or finding?\n"
                    "   (Good: 'Revenue growth by quarter 2023-2024'. "
                    "Bad: 'Revenue chart')\n"
                    "2. Adds value beyond a number/table: Does the chart add "
                    "value over a simple number or table by answering that "
                    "question visually, rather than showing data for its own "
                    "sake?\n\n"
                    "Score 1.0 when the title states a specific question and "
                    "the chart adds visual value beyond a number/table. "
                    "Score 0.5 when only one dimension holds (e.g. useful chart "
                    "but generic title). "
                    "Score 0.0 when the chart is purposeless or its title is "
                    "just a variable name." + EVIDENCE_INSTRUCTION
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
