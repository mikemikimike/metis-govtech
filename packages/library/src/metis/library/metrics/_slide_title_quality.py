"""Slide Title Quality metric (M-SM-15)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import DeckSlide, extract_deck_slides
from ._judge import _get_judge_model


def _render_slides(slides: list[DeckSlide]) -> str:
    parts = []
    for s in slides:
        body = "\n".join(f"    - {line}" for line in s.body)
        parts.append(f"Slide {s.index + 1} title: {s.title}\n{body}".rstrip())
    return "\n".join(parts)


class SlideTitleQualityMetric(MetisTurnMetric):
    """Titles describe content and form a coherent sequence? (M-SM-15)

    Judge-graded across two dimensions: (1) each title accurately describes
    its slide's content; (2) the titles read in order form a coherent
    sequence. Uses the extracted slide title/body text. Skips when no deck is
    extractable.
    """

    tags: ClassVar[tuple[str, ...]] = ("presentation", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Slide Title Quality",
                model=_get_judge_model(),
                criteria=(
                    "Slide titles should accurately describe their slide's "
                    "content and, read in order, form a coherent sequence; "
                    "compare the slide titles against their body text and read "
                    "them as an ordered sequence, judging title-to-content "
                    "accuracy and the coherence of the title sequence.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "each slide's title and body text in order; the "
                    "'actual_output' is the agent's response.\n\n"
                    "Assess two dimensions:\n"
                    "1. Title accuracy: Does each title accurately describe the "
                    "content of its slide (not generic or misleading)?\n"
                    "2. Sequence coherence: Read top to bottom, do the titles "
                    "form a coherent sequence that tells the deck's story?\n\n"
                    "Score 1.0 when titles are accurate and the sequence is "
                    "coherent. "
                    "Score 0.5 when one dimension is weak. "
                    "Score 0.0 when titles are generic/misleading or the "
                    "sequence is incoherent." + EVIDENCE_INSTRUCTION
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
        self, test_case: LLMTestCase, slides: list[DeckSlide]
    ) -> LLMTestCase:
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=["Deck slides:\n" + _render_slides(slides)],
            metadata=test_case.metadata,
        )

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        slides = extract_deck_slides(test_case)
        if not slides:
            return mark_skipped(
                self, "no deck extractable; title quality cannot be assessed."
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, slides))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Slide Title Quality"

    def is_successful(self) -> bool:
        return self.success is True
