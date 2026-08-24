"""M-UNI-9: Failure Report Quality metric."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model
from ._types import OrcaChatMetadata, TraceMetadata


class FailureReportQualityMetric(MetisTurnMetric):
    """Report includes what failed, what was attempted, and next steps?

    Full judge: evaluates the agent's failure report when it stops on an error.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "universal",
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
                name="Failure Report Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the quality of the agent's "
                    "failure report to the user.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' is the agent's "
                    "failure report.\n\n"
                    "A good failure report must include "
                    "ALL THREE:\n"
                    "1. What failed: Clear description "
                    "of the error or obstacle\n"
                    "2. What was attempted: What the "
                    "agent tried before giving up\n"
                    "3. Actionable next steps: At least "
                    "one concrete suggestion for the "
                    "user\n\n"
                    "Score 1.0 if all three present and clear. "
                    "Score 0.5 if two of three present. "
                    "Score 0.0 if only one or none — e.g. just says 'I couldn't do it'."
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
        metadata = cast(TraceMetadata, test_case.metadata)
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )

        if not chat_meta.had_error:
            return mark_skipped(self, "No error in this trace")

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
        return "Failure Report Quality"

    def is_successful(self) -> bool:
        return self.success is True
