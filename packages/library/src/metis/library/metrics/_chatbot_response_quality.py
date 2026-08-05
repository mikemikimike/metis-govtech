"""Chatbot Response Quality metric (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
from ._judge import _get_judge_model
from ._types import TraceMetadata


class ChatbotResponseQualityMetric(SyncBaseMetric):
    """Direct response helpful, appropriate tone, and concise?

    Full judge: evaluates Orca's quality when handling requests directly
    (no delegation). Skips if delegation occurred.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
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
                name="Chatbot Response Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the orchestrator's direct response "
                    "(no subagent was used).\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "direct response.\n\n"
                    "Rate on three dimensions:\n"
                    "1. Helpful: Does it actually answer the "
                    "question or address the need?\n"
                    "2. Tone: Is the tone appropriate "
                    "(professional, friendly, matches "
                    "context)?\n"
                    "3. Concise: Is it appropriately brief "
                    "without being curt?\n\n"
                    "Score 1.0 if excellent on all dimensions. "
                    "Score 0.5 if helpful but verbose, or "
                    "concise but off-tone. "
                    "Score 0.0 if unhelpful, inappropriate, "
                    "or incomprehensible." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        if delegation and delegation.get("target"):
            self.score = 1.0
            self.skipped = True
            self.reason = "Delegation occurred (not a direct-handle case) — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        if delegation and delegation.get("target"):
            self.score = 1.0
            self.skipped = True
            self.reason = "Delegation occurred (not a direct-handle case) — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Chatbot Response Quality"

    def is_successful(self) -> bool:
        return self.success is True
