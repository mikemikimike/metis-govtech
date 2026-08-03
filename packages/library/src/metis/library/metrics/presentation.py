"""
Slide Maker agent metrics (M-SM-*).

Core metrics (AC-SM-11, AC-SM-14, AC-SM-18):
  Slide spec compliance        — Extract + GEval judge
  Cross-slide logical flow     — Full GEval judge
  Deck source faithfulness     — Extract + GEval judge
"""

from typing import cast

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams

from metis.library.metrics._types import TraceMetadata

from ._judge import _get_judge_model
from .universal import (
    EVIDENCE_INSTRUCTION,
    SyncBaseMetric,
    _ContextAwareGEval,
    _with_eval_context,
)


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


def _extract_source_facts(test_case: LLMTestCase) -> list:
    """Pull source file contents from read_source_file tool call outputs."""
    metadata = cast(TraceMetadata, test_case.metadata)
    observations = metadata.get("observations", [])
    source_texts = []

    for obs in observations:
        tool_name = obs.get("name", "")
        if "read_source" in tool_name or "source_file" in tool_name:
            output = obs.get("output")
            if output and isinstance(output, str):
                source_texts.append(output)
            elif output and isinstance(output, dict):
                content = output.get("content") or output.get("text") or ""
                if content:
                    source_texts.append(content)

    return source_texts


class SlideSpecComplianceMetric(SyncBaseMetric):
    """AC-SM-11 — Slide spec compliance.

    Checks whether the generated deck meets explicit user specifications:
    slide count, theme, and any other instructions the user stated.
    Extracts deck properties from trace metadata (make_ppt outputs) and
    passes them as judge context alongside the original request.
    Skips if no deck properties are extractable.
    """

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

    def measure(self, test_case: LLMTestCase) -> float:
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
            self.score = 1.0
            self.skipped = True
            self.reason = "No deck properties extractable from trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        context_str = "\n".join(context_parts)
        spec_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[context_str],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        geval.measure(spec_tc)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Slide Spec Compliance"

    def is_successful(self) -> bool:
        return self.success is True


class CrossSlideLogicalFlowMetric(SyncBaseMetric):
    """AC-SM-14 — Cross-slide logical flow.

    Evaluates narrative coherence across slides: does slide N+1 logically
    follow from slide N, and does the deck tell a unified story?
    Uses slide titles (and first-level content if available) as input.
    Skips if no slide structure is extractable.
    """

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


class DeckSourceFaithfulnessMetric(SyncBaseMetric):
    """AC-SM-18 — Deck source faithfulness.

    Does the deck contradict or misrepresent facts from the source material?
    Extracts source file contents from read_source_file tool calls and passes
    them as retrieval_context to DeepEval's built-in FaithfulnessMetric.
    Skips if no source material is found in the trace.
    """

    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = FaithfulnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        source_texts = _extract_source_facts(test_case)

        if not source_texts and test_case.context:
            source_texts = list(test_case.context)

        if not source_texts:
            self.score = 1.0
            self.skipped = True
            self.reason = "No source material found in trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        combined_source = "\n\n---\n\n".join(source_texts)
        faith_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                retrieval_context=[combined_source],
                metadata=test_case.metadata,
            )
        )

        metric = self._get_metric()
        metric.measure(faith_tc)
        self.score = metric.score
        self.evaluation_cost = getattr(metric, "evaluation_cost", None)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Deck Source Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
