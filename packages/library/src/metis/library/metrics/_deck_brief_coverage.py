"""Deck Brief Coverage metric (M-SM-11)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
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


class DeckBriefCoverageMetric(MetisTurnMetric):
    """Deck covers all brief content? (M-SM-11)

    Extract-and-judge. Compares the brief's content against the extracted
    slide title/body text of the deck and scores coverage. Falls back to the
    user request when no explicit brief is observable. Skips when no deck is
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
                name="Deck Brief Coverage",
                model=_get_judge_model(),
                criteria=(
                    "The generated deck should cover all the content specified "
                    "in the brief; compare the brief's content against the "
                    "slide titles and body text of the generated deck and "
                    "judge whether every content point in the brief is "
                    "represented somewhere in the deck.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the brief content and the deck's slide title/body text; "
                    "the 'actual_output' is the agent's response.\n\n"
                    "Assess whether the deck covers all the content specified "
                    "in the brief — each key point should appear somewhere in "
                    "the slides.\n\n"
                    "Score 1.0 when all brief content is covered. "
                    "Score 0.5 when the main points are covered but some are "
                    "missing. "
                    "Score 0.0 when significant brief content is absent from "
                    "the deck." + EVIDENCE_INSTRUCTION
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
        self, test_case: LLMTestCase, brief: str, slides: list[DeckSlide]
    ) -> LLMTestCase:
        context = (
            "Brief content:\n" + brief + "\n\nDeck slides:\n" + _render_slides(slides)
        )
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[context],
            metadata=test_case.metadata,
        )

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        slides = extract_deck_slides(test_case)
        if not slides:
            return mark_skipped(
                self, "no deck extractable; brief coverage cannot be assessed."
            )
        brief = extract_brief(test_case) or (test_case.input or "")
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, brief, slides))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Deck Brief Coverage"

    def is_successful(self) -> bool:
        return self.success is True
