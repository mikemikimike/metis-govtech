"""Report Coherence metric (M-DA-13)."""

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


class ReportCoherenceMetric(MetisMetric):
    """Report sections follow a logical structure?

    Skips when output is too short to be a report or not from data analyst.
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

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        if not _has_report_content(test_case):
            return mark_skipped(
                self, "Output too short or not from data analyst — not a report"
            )

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
        return "Report Coherence"

    def is_successful(self) -> bool:
        return self.success is True
