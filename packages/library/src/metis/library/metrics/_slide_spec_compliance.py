"""Slide Spec Compliance metric (AC-SM-11)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisMetric, _ContextAwareGEval, mark_skipped
from ._judge import _get_judge_model
from ._types import TraceMetadata


def _extract_deck_properties(test_case: LLMTestCase) -> dict:
    """Pull slide count, theme, and titles from trace metadata or observations."""
    metadata = cast(TraceMetadata, test_case.metadata)
    observations = metadata.get("observations", [])

    deck_props = {
        "slide_count": None,
        "theme": None,
        "slide_titles": [],
        "deck_content_summary": "",
    }

    for obs in observations:
        obs_meta = obs.get("metadata") or {}
        deck_meta = obs_meta.get("deck_metadata", {})
        if "slide_count" in deck_meta:
            deck_props["slide_count"] = deck_meta["slide_count"]
        if "theme" in deck_meta:
            deck_props["theme"] = deck_meta["theme"]
        if "slide_titles" in deck_meta:
            deck_props["slide_titles"] = deck_meta["slide_titles"]

        output = obs.get("output")
        if isinstance(output, dict):
            if "slide_count" in output and deck_props["slide_count"] is None:
                deck_props["slide_count"] = output["slide_count"]
            if "theme" in output and deck_props["theme"] is None:
                deck_props["theme"] = output["theme"]
            if "slides" in output and not deck_props["slide_titles"]:
                slides = output["slides"]
                if isinstance(slides, list):
                    deck_props["slide_titles"] = [
                        s.get("title", "") for s in slides if isinstance(s, dict)
                    ]

        if isinstance(output, str) and "pptx" in output.lower():
            deck_props["deck_content_summary"] = output

    return deck_props


class SlideSpecComplianceMetric(MetisMetric):
    """AC-SM-11 — Slide spec compliance.

    Checks whether the generated deck meets explicit user specifications:
    slide count, theme, and any other instructions the user stated.
    Extracts deck properties from trace metadata (make_ppt outputs) and
    passes them as judge context alongside the original request.
    Skips if no deck properties are extractable.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "presentation",
        "per-turn",
        "judge-graded",
    )

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Slide Spec Compliance",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the generated presentation "
                    "meets the user's explicit specifications.\n\n"
                    "The 'input' is the user's original request "
                    "(which may specify slide count, theme, "
                    "and other requirements).\n"
                    "The 'actual_output' is the Slide Maker's "
                    "confirmation or summary of what was "
                    "produced.\n"
                    "The 'context' contains the extracted deck "
                    "properties: slide count, theme applied, "
                    "and slide titles.\n\n"
                    "CHECK EACH EXPLICIT REQUIREMENT:\n"
                    "1. Slide count: If the user specified a "
                    "number (e.g. '10 slides'), did the deck "
                    "have that many? ±1 is acceptable if not "
                    "explicitly required exactly.\n"
                    "2. Theme: If the user specified a theme "
                    "name, was it applied?\n"
                    "3. Custom instructions: Any other explicit "
                    "requirements (include X section, "
                    "use Y format, avoid Z) — were they "
                    "followed?\n\n"
                    "Score 1.0 if all explicit requirements "
                    "met. "
                    "Score 0.5 if partial compliance (some "
                    "requirements met, some missed). "
                    "Score 0.0 if key requirements clearly "
                    "violated.\n"
                    "If the user gave no explicit "
                    "specifications, score 1.0 (nothing to "
                    "violate)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.CONTEXT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        deck_props = _extract_deck_properties(test_case)

        context_parts = []
        if deck_props["slide_count"] is not None:
            context_parts.append(f"Slide count: {deck_props['slide_count']}")
        if deck_props["theme"]:
            context_parts.append(f"Theme applied: {deck_props['theme']}")
        if deck_props["slide_titles"]:
            titles_str = "\n".join(
                f"  {i + 1}. {t}" for i, t in enumerate(deck_props["slide_titles"])
            )
            context_parts.append(f"Slide titles:\n{titles_str}")

        if not context_parts:
            return mark_skipped(self, "No deck properties extractable from trace")

        context_str = "\n".join(context_parts)
        spec_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[context_str],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(spec_tc)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Slide Spec Compliance"

    def is_successful(self) -> bool:
        return self.success is True
