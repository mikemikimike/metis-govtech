"""Deck Audience Calibration grader (M-SM-19)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnGrader,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import DeckSlide, extract_brief, extract_deck_slides
from ._judge import _get_judge_model


def _render_slides(slides: list[DeckSlide]) -> str:
    parts = []
    for s in slides:
        body = "\n".join(f"    - {line}" for line in s.body)
        parts.append(f"Slide {s.index + 1}: {s.title}\n{body}".rstrip())
    return "\n".join(parts)


class DeckAudienceCalibrationGrader(MetisTurnGrader):
    """Density, jargon, and depth suited to the stated audience? (M-SM-19)

    Judge-graded across three dimensions: density, jargon, and depth, each
    calibrated to the stated target audience. Uses the extracted slide
    title/body text and the brief (for the audience). Skips when no deck is
    extractable.
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
                name="Deck Audience Calibration",
                model=_get_judge_model(),
                criteria=(
                    "The deck's density, jargon, and depth should be "
                    "calibrated to the stated target audience; read the deck's "
                    "slide title/body text against the stated audience and "
                    "judge the three calibration dimensions — density, jargon, "
                    "and depth — against that audience.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the stated audience (from the brief) and the deck's slide "
                    "title/body text; the 'actual_output' is the agent's "
                    "response.\n\n"
                    "Assess three dimensions against the target audience:\n"
                    "1. Density: Is the amount of content per slide suited to "
                    "the audience?\n"
                    "2. Jargon: Is the level of technical language "
                    "appropriate?\n"
                    "3. Depth: Is the depth of explanation right for the "
                    "audience?\n\n"
                    "Score 1.0 when all three are well calibrated. "
                    "Score 0.5 when one dimension is off. "
                    "Score 0.0 when two or more are mismatched to the "
                    "audience. If no audience is stated, judge against a "
                    "reasonable general audience." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(
        self, test_case: LLMTestCase, slides: list[DeckSlide], brief: str
    ) -> LLMTestCase:
        audience = (
            "Stated audience (from brief):\n" + brief
            if brief
            else ("Stated audience: not explicitly stated.")
        )
        context = audience + "\n\nDeck slides:\n" + _render_slides(slides)
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[context],
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        slides = extract_deck_slides(test_case)
        if not slides:
            return mark_skipped(
                self,
                "no deck extractable; audience calibration cannot be assessed.",
            )
        brief = extract_brief(test_case) or ""
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, slides, brief))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Deck Audience Calibration"

    def is_successful(self) -> bool:
        return self.success is True
