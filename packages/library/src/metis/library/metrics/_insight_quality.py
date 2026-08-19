"""Insight Quality metric (M-DA-5)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisMetric, _ContextAwareGEval, mark_skipped
from ._judge import _get_judge_model
from ._types import OrcaChatMetadata, TraceMetadata


def _is_data_analyst_trace(test_case: LLMTestCase) -> bool:
    """Check if this trace was routed to the data analyst subagent."""
    metadata = cast(TraceMetadata, test_case.metadata)
    delegation = metadata.get("delegation")
    target = delegation["target"] if delegation else ""
    if "data" in target.lower():
        return True
    chat_meta: OrcaChatMetadata = metadata.get("chat_metadata") or OrcaChatMetadata()
    routed = chat_meta.routed_to_agents
    return bool(any("data" in str(a).lower() for a in routed))


def _has_report_content(test_case: LLMTestCase) -> bool:
    """Check if the output is long enough to be a report."""
    output = test_case.actual_output or ""
    return len(output) > 500 and _is_data_analyst_trace(test_case)


class InsightQualityMetric(MetisMetric):
    """Insights precise, grounded, not overclaiming, relevant, actionable?"""

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

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        if not _has_report_content(test_case):
            return mark_skipped(self, "Judge did not receive report/analysis content")

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
        return "Insight Quality"

    def is_successful(self) -> bool:
        return self.success is True
