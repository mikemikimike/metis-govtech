"""Brief Audience Appropriateness metric (M-SM-9)."""

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


class BriefAudienceAppropriatenessMetric(MetisTurnMetric):
    """Brief detail appropriate for the stated audience? (M-SM-9)

    Extract-and-judge. Assesses whether the extracted brief's detail level
    matches its stated audience and purpose. Skips when no brief is
    observable.
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
                name="Brief Audience Appropriateness",
                model=_get_judge_model(),
                criteria=(
                    "The brief's detail level matches the demands of its "
                    "stated audience and purpose; judge whether the brief's "
                    "depth and detail are calibrated to the audience and "
                    "purpose it names.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the extracted brief; the 'actual_output' is the agent's "
                    "response.\n\n"
                    "Assess whether the brief's detail level fits the audience "
                    "and purpose it states — for example, an executive "
                    "audience needs concise, high-level framing, while a "
                    "technical audience can take more depth.\n\n"
                    "Score 1.0 when the detail level clearly matches the "
                    "stated audience and purpose. "
                    "Score 0.5 when it is roughly appropriate but somewhat too "
                    "shallow or too detailed. "
                    "Score 0.0 when the detail level is clearly mismatched to "
                    "the audience/purpose." + EVIDENCE_INSTRUCTION
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
                self,
                "no brief observed; audience appropriateness cannot be assessed.",
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
        return "Brief Audience Appropriateness"

    def is_successful(self) -> bool:
        return self.success is True
