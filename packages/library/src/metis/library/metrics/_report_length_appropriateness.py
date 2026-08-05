"""Report Length Appropriateness metric (M-DA-20)."""

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


class ReportLengthAppropriatenessMetric(SyncBaseMetric):
    """Report length proportionate to query scope?"""

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
