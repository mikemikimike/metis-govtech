"""Follow-Up Relevance metric (M-ORCA-*)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model


class FollowUpRelevanceMetric(MetisTurnMetric):
    """Follow-up suggestions relevant and actionable?

    Full judge: evaluates the quality of follow-up suggestions offered
    at the end of a completed task. Skips mid-flow turns (form presentations,
    job submissions, status updates) where follow-ups are not expected.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "judge-graded",
    )

    MIDFLOW_SIGNALS = [
        "form",
        "fill in",
        "fill out",
        "please fill",
        "pick a",
        "is now running",
        "job submitted",
        "track progress",
    ]

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _is_midflow_response(self, test_case: LLMTestCase) -> bool:
        output_lower = (test_case.actual_output or "").lower()
        return any(signal in output_lower for signal in self.MIDFLOW_SIGNALS)

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Follow-Up Relevance",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the follow-up suggestions the "
                    "orchestrator offers after completing a "
                    "task.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "response (look for follow-up suggestions "
                    "at the end — questions, next steps, or "
                    "related actions offered to the user).\n\n"
                    "Check:\n"
                    "1. Are follow-up suggestions present?\n"
                    "2. Are they relevant to what was just "
                    "accomplished (not generic)?\n"
                    "3. Are they actionable (user could "
                    "actually do them as a next step)?\n\n"
                    "Score 1.0 if follow-ups are relevant and "
                    "actionable. "
                    "Score 0.7 if the task is clearly complete "
                    "and no follow-ups are needed "
                    "(simple confirmations, status updates). "
                    "Score 0.5 if present but generic ('let me "
                    "know if you need anything else'). "
                    "Score 0.0 ONLY if the response delivers "
                    "substantial results (analysis, report, "
                    "findings) but offers zero guidance on "
                    "what to do next, AND the user would "
                    "clearly benefit from suggestions." + EVIDENCE_INSTRUCTION
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
        if self._is_midflow_response(test_case):
            return mark_skipped(
                self,
                "Mid-flow response (form/status/job submission) — follow-ups not expected",
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
        return "Follow-Up Relevance"

    def is_successful(self) -> bool:
        return self.success is True
