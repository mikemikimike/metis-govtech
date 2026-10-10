"""Re-delegation on Failure grader (M-ORCA-*)."""

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


class RedelegationOnFailureGrader(MetisTurnGrader):
    """Re-delegates or tries different subagent after bad output?

    Extract+judge: checks whether Orca re-delegated when subagent output was poor.
    Skips if no delegation occurred or subagent output looks fine.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
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
                name="Re-delegation on Failure",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator "
                    "appropriately handled a subagent's "
                    "poor or incomplete output.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "final response.\n"
                    "The 'context' contains the subagent's raw "
                    "output.\n\n"
                    "Check:\n"
                    "1. Was the subagent output actually "
                    "deficient (off-topic, incomplete, "
                    "wrong)?\n"
                    "2. If yes, did the orchestrator detect the "
                    "problem?\n"
                    "3. Did it re-delegate, try a different "
                    "approach, or supplement the output?\n\n"
                    "Score 1.0 if subagent output was good (no "
                    "recovery needed), or if the "
                    "orchestrator correctly detected and "
                    "recovered from bad output. "
                    "Score 0.5 if it partially recovered "
                    "(noted issues but still passed through "
                    "flawed content). "
                    "Score 0.0 if it blindly relayed clearly "
                    "deficient subagent output." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.CONTEXT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata)
        delegation = metadata.get("delegation")

        subagent_output = delegation.get("response", "") if delegation else ""
        if not subagent_output and test_case.context:
            subagent_output = test_case.context[0]

        if not subagent_output:
            return mark_skipped(self, "No subagent output to evaluate recovery")

        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[subagent_output],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(judge_tc)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Re-delegation on Failure"

    def is_successful(self) -> bool:
        return self.success is True
