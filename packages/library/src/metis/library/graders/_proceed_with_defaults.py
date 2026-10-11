"""Proceed With Defaults grader (M-DA-28)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisTurnGrader, _ContextAwareGEval
from ._judge import _get_judge_model


class ProceedWithDefaultsGrader(MetisTurnGrader):
    """Did the agent proceed with a sensible default and offer follow-ups?

    Judge-graded (M-DA-28). For an ambiguous request, scores full marks when
    the agent proceeds with a reasonable, explicitly stated default and offers
    follow-up options rather than blocking on a clarifying question.
    """

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Proceed With Defaults",
                model=_get_judge_model(),
                criteria=(
                    "On an ambiguous request, the agent should proceed with a "
                    "reasonable, stated default and offer follow-up options "
                    "rather than blocking, keeping the user in control; judge "
                    "the agent's response to the under-specified request for "
                    "whether it states a default, acts on it, and offers "
                    "follow-ups instead of only asking the user to "
                    "clarify.\n\n"
                    "The 'input' is the user's (ambiguous) request; the "
                    "'actual_output' is the agent's response.\n\n"
                    "Assess three dimensions:\n"
                    "1. Stated default: Does the response choose and clearly "
                    "state a reasonable default interpretation?\n"
                    "2. Proceeds, not blocks: Does it act on that default and "
                    "deliver progress, rather than only asking the user to "
                    "clarify before doing anything?\n"
                    "3. Offers follow-ups: Does it offer options or "
                    "next-step adjustments so the user stays in control?\n\n"
                    "Score 1.0 when it states a default, proceeds, and offers "
                    "follow-ups. "
                    "Score 0.5 when it proceeds but omits the stated default "
                    "or follow-up options. "
                    "Score 0.0 when it blocks on clarification without "
                    "proceeding, or proceeds silently with no stated default "
                    "and no options.\n"
                    "If the request was not actually ambiguous, score 1.0 "
                    "(nothing to default)." + EVIDENCE_INSTRUCTION
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
        return "Proceed With Defaults"

    def is_successful(self) -> bool:
        return self.success is True
