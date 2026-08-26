"""Delegation Quality metric (M-ORCA-*)."""

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


class DelegationQualityMetric(MetisTurnMetric):
    """Delegation Quality (span-aware wrapper for GEval).

    Extracts the delegation task message from the span tree and evaluates
    it with a GEval judge. If no delegation occurred, skips.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "judge-graded",
    )

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Delegation Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the task description that the "
                    "orchestrator passes to its subagent.\n\n"
                    "The 'input' is the user's original request.\n"
                    "The 'actual_output' is the delegation "
                    "message/instruction sent to the "
                    "subagent.\n\n"
                    "Rate on four dimensions:\n"
                    "1. Clarity: Is the task description "
                    "unambiguous?\n"
                    "2. Comprehensiveness: Does it include all "
                    "necessary info (file names, "
                    "specific quantities, user constraints)?\n"
                    "3. Relevance: Does it faithfully represent "
                    "the user's request without "
                    "scope creep or narrowing?\n"
                    "4. Feasibility: Is the task achievable by "
                    "the target subagent?\n\n"
                    "Score 0.0 if critically deficient. "
                    "Score 0.5 if adequate. "
                    "Score 1.0 if excellent on all dimensions." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(LlmTestCaseMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        if not delegation or not delegation["task"]:
            return mark_skipped(self, "No delegation occurred or no task message found")

        delegation_tc = LLMTestCase(
            input=test_case.input,
            actual_output=delegation["task"],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(delegation_tc)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = f"[→ {delegation['target']}] {geval.reason}"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Delegation Quality"

    def is_successful(self) -> bool:
        return self.success is True
