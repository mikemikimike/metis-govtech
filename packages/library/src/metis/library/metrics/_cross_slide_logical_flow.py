"""Cross-Slide Logical Flow metric (AC-SM-14)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
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


class CrossSlideLogicalFlowMetric(SyncBaseMetric):
    """AC-SM-14 — Cross-slide logical flow.

    Evaluates narrative coherence across slides: does slide N+1 logically
    follow from slide N, and does the deck tell a unified story?
    Uses slide titles (and first-level content if available) as input.
    Skips if no slide structure is extractable.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "presentation",
        "per-turn",
        "judge-graded",
        "condition-gated",
    )
    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Cross-Slide Logical Flow",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the narrative coherence of the "
                    "presentation's slide sequence.\n\n"
                    "The 'input' is the user's original request "
                    "(the brief).\n"
                    "The 'context' contains the numbered slide "
                    "titles and any first-level content.\n\n"
                    "WHAT TO ASSESS:\n"
                    "1. Does the deck have a logical structure? "
                    "(e.g. intro -> problem -> solution -> "
                    "evidence -> conclusion, or another coherent"
                    " arc appropriate for the brief)\n"
                    "2. Do adjacent slides connect naturally — "
                    "does slide N+1 follow from slide N "
                    "without jarring topic jumps?\n"
                    "3. Does the deck tell a unified story that"
                    " addresses the brief, rather than "
                    "being a disconnected list of topics?\n\n"
                    "Score 1.0 if the deck has clear, logical "
                    "flow throughout. "
                    "Score 0.5 if mostly coherent but with one "
                    "jarring transition or missing section. "
                    "Score 0.0 if slides feel randomly ordered "
                    "or the narrative is incoherent." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        deck_props = _extract_deck_properties(test_case)

        if not deck_props["slide_titles"]:
            self.score = 1.0
            self.skipped = True
            self.reason = "No slide titles extractable from trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        titles_str = "\n".join(
            f"{i + 1}. {t}" for i, t in enumerate(deck_props["slide_titles"])
        )
        context_str = (
            f"Slide sequence ({len(deck_props['slide_titles'])} slides):\n{titles_str}"
        )

        flow_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[context_str],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        geval.measure(flow_tc)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Cross-Slide Logical Flow"

    def is_successful(self) -> bool:
        return self.success is True
