"""Brief Goal Details metric (M-SM-2)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import extract_brief
from ._judge import _get_judge_model


class BriefGoalDetailsMetric(MetisTurnMetric):
    """Goal is one sentence naming audience, intent, and tone? (M-SM-2)

    Judge-graded. Uses the extracted brief. Scores full marks when the deck
    goal is a single sentence that names the audience, the intent, and the
    tone. Skips when no brief is observable.
    """

    tags: ClassVar[tuple[str, ...]] = ("presentation", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Brief Goal Details",
                model=_get_judge_model(),
                criteria=(
                    "The brief's deck goal is a single outcome-oriented "
                    "sentence that names the audience, the intent, and the "
                    "tone; judge the goal field of the brief for a "
                    "single-sentence form that mentions audience, intent, and "
                    "tone.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the extracted brief; the 'actual_output' is the agent's "
                    "response.\n\n"
                    "Focus on the brief's deck goal and assess:\n"
                    "1. Audience: Does the goal name the intended audience?\n"
                    "2. Intent: Does it state the intent/purpose of the deck?\n"
                    "3. Tone: Does it state the tone?\n"
                    "Also check the goal is a single, focused sentence.\n\n"
                    "Score 1.0 when the goal is one sentence naming audience, "
                    "intent, and tone. "
                    "Score 0.5 when one of the three is missing or the goal "
                    "sprawls beyond a sentence. "
                    "Score 0.0 when two or more are missing." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase, brief: str) -> LLMTestCase:
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=["Extracted brief:\n" + brief],
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        brief = extract_brief(test_case)
        if not brief:
            return mark_skipped(
                self, "no brief observed; the deck goal cannot be assessed."
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, brief))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Brief Goal Details"

    def is_successful(self) -> bool:
        return self.success is True
