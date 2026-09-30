"""Slide Visual Quality metric (M-SM-13)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import get_deck_slide_images
from ._judge import _get_judge_model


def _image_markers(refs: list[str]) -> list[str]:
    """Turn slide-image refs into deepeval multimodal markers.

    Each ref is registered as an ``MLLMImage`` when possible so its bytes are
    loaded for the judge; if the ref cannot be loaded (missing file or invalid
    URL), a raw ``[DEEPEVAL:IMAGE:<ref>]`` marker is used so the deck still
    reads as multimodal and the judge receives the reference.
    """
    from deepeval.test_case.llm_test_case import MLLMImage

    markers: list[str] = []
    for ref in refs:
        try:
            markers.append(str(MLLMImage(url=ref)))
        except Exception:
            markers.append(f"[DEEPEVAL:IMAGE:{ref}]")
    return markers


class SlideVisualQualityMetric(MetisTurnMetric):
    """Layout, balance, decoration, and legibility of rendered slides? (M-SM-13)

    Multimodal judge-graded across four dimensions: (1) layout consistency;
    (2) text-visual balance; (3) decorative restraint; (4) text legibility.
    Reads the most recently delivered target deck artifact that is already a
    ``.pdf`` and renders each page via ``pymupdf`` (see
    ``get_deck_slide_images``). A target artifact delivered only as
    ``.pptx``, with no accompanying ``.pdf``, has no local conversion path —
    METIS does not shell out to a system-level renderer for this — so that
    case always skips too, same as when no deck artifact exists at all. This
    is a real, current limitation, not a hypothetical one.

    The PDF is rasterized to PNGs rather than handed to the judge as-is:
    DeepEval's multimodal test case is built from ``MLLMImage``, which is
    typed around image formats, not documents, so the judge model never
    sees a PDF as such regardless of whether the model behind it could
    otherwise read one. Rendering ourselves also fixes the DPI explicitly
    (see ``render_pdf_slides``) and gives a stable, ordered list of
    per-page images to match the judge criteria's own "look at the slide
    images, in order" framing — both of which a model's internal PDF
    rasterizer would leave opaque.
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
                name="Slide Visual Quality",
                model=_get_judge_model(),
                criteria=(
                    "The rendered slides should have a consistent layout, an "
                    "appropriate text-visual balance, restrained decoration, "
                    "and legible text; look at the pre-rendered slide images of "
                    "the generated deck and judge the four visual dimensions — "
                    "layout consistency, text-visual balance, decorative "
                    "restraint, and text legibility.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the pre-rendered slide images of the deck in order; the "
                    "'actual_output' is the agent's response.\n\n"
                    "Look at the slide images and assess four dimensions:\n"
                    "1. Layout consistency: Do the slides share a consistent "
                    "layout (alignment, margins, placement)?\n"
                    "2. Text-visual balance: Is the balance between text and "
                    "visuals appropriate — neither wall-of-text nor empty?\n"
                    "3. Decorative restraint: Are decorative elements "
                    "restrained rather than cluttering the slides?\n"
                    "4. Text legibility: Is all text legible (size, contrast, "
                    "not overflowing or truncated)?\n\n"
                    "Score 1.0 when all four dimensions are satisfied. "
                    "Score 0.5 when one or two dimensions are weak. "
                    "Score 0.0 when three or more are poor." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase, refs: list[str]) -> LLMTestCase:
        context = ["Rendered slide images (in order):", *_image_markers(refs)]
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=context,
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        refs = get_deck_slide_images(test_case)
        if not refs:
            return mark_skipped(
                self,
                "no renderable PDF deck artifact available; visual quality "
                "cannot be assessed.",
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, refs))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Slide Visual Quality"

    def is_successful(self) -> bool:
        return self.success is True
