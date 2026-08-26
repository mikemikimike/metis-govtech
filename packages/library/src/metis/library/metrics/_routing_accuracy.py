"""Routing Accuracy metric (M-ORCA-*)."""

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


class RoutingAccuracyMetric(MetisTurnMetric):
    """Right subagent chosen?

    LLM judge evaluates whether the chosen subagent (or direct handling) was
    appropriate for the user's request. No annotations needed.
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
                name="Routing Accuracy",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator routed the "
                    "user's request to the "
                    "correct subagent (or handled it directly when "
                    "appropriate).\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is what the orchestrator "
                    "did — its response shows "
                    "which agent handled the task (look for "
                    "mentions of 'Data Analyst', "
                    "'Slide Maker', or direct handling).\n\n"
                    "Available agents:\n"
                    "- Data Analyst: for data analysis, charts, "
                    "statistics, reports from data\n"
                    "- Slide Maker: for creating "
                    "presentations/slide decks\n"
                    "- Direct handling: for simple questions, "
                    "greetings, meta-questions about "
                    "capabilities\n\n"
                    "Score 1.0 if the routing was clearly correct. "
                    "Score 0.5 if the choice was defensible but "
                    "suboptimal. "
                    "Score 0.0 if clearly wrong (e.g. sent a data "
                    "question to Slide Maker)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _has_routing_decision(self, test_case: LLMTestCase) -> bool:
        """A routing decision occurred if delegation is present OR tool calls were made.

        A trace with no delegation and no tool calls (e.g. a greeting) had no
        routing decision to evaluate — the agent just responded directly without
        invoking anything.
        """
        metadata = cast(LlmTestCaseMetadata, test_case.metadata)
        if metadata.get("delegation"):
            return True
        return bool(metadata.get("tool_calls"))

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        if not self._has_routing_decision(test_case):
            return mark_skipped(
                self,
                "No routing decision in this trace (no delegation, no tool calls)",
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
        return "Routing Accuracy"

    def is_successful(self) -> bool:
        return self.success is True
