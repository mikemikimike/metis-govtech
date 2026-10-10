"""Chart Necessity / gating grader (M-DA-22)."""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnGrader,
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


class ChartNecessityGrader(MetisTurnGrader):
    """Chart adds value beyond a simple number/table?

    Chart gating / restraint: a produced chart must be warranted — the agent
    should default to text/tables for non-chart or ambiguous asks and never
    produce unrequested dashboards or 2x2 grids. Skips when no chart content
    is present (the restraint decision to not chart is not penalised here).
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
                name="Chart Necessity",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether producing this chart was warranted — "
                    "i.e. whether the agent showed appropriate charting "
                    "restraint.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' describes the chart and the "
                    "data it visualises.\n\n"
                    "Check:\n"
                    "1. Was a chart warranted — either explicitly requested, "
                    "or revealing a non-obvious insight that text/a table "
                    "would not convey as well?\n"
                    "2. For a non-chart or ambiguous ask, would text or a "
                    "table have been the more appropriate default?\n"
                    "3. Is this an unrequested dashboard, 2x2 grid, or "
                    "exploratory chart produced without being asked?\n\n"
                    "Score 1.0 when the chart was clearly warranted. "
                    "Score 0.5 when a chart is defensible but text/a table "
                    "would have served as well. "
                    "Score 0.0 when the chart was unwarranted — an unrequested "
                    "dashboard/grid, or a case where a single number or table "
                    "should have been the default." + EVIDENCE_INSTRUCTION
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
        return "Chart Necessity"

    def is_successful(self) -> bool:
        return self.success is True
