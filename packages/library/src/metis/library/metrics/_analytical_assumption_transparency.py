"""Analytical Assumption Transparency metric (M-DA-18)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
from ._judge import _get_judge_model
from ._types import OrcaChatMetadata, TraceMetadata


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


def _has_report_content(test_case: LLMTestCase) -> bool:
    """Check if the output is long enough to be a report."""
    output = test_case.actual_output or ""
    return len(output) > 500 and _is_data_analyst_trace(test_case)


class AnalyticalAssumptionTransparencyMetric(SyncBaseMetric):
    """Analytical/methodological assumptions explicitly stated?

    Skips when trace is not from data analyst or output is too short.
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
