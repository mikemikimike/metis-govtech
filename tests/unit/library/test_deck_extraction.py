"""Portable PPTX text extraction and deck-consuming metric wiring.

Reads slide text through the stdlib ZIP/XML representation (no presentation
library, no network) and checks that deck metrics consume the extracted
slides and skip cleanly when no deck exists.
"""

import asyncio

from metis.library.metrics import (
    CrossSlideLogicalFlowMetric,
    SlideSpecComplianceMetric,
    SlideTitleQualityMetric,
)
from metis.library.metrics._extraction import extract_deck_slides, read_pptx_slides

from .conftest import artifact, make_case


def test_read_pptx_slides_orders_and_splits_title_body(pptx_factory):
    path = pptx_factory(
        [
            ["Revenue Overview", "Q1 grew 12%", "Q2 grew 8%"],
            ["Regional Breakdown", "APAC led growth"],
        ]
    )
    slides = read_pptx_slides(path)
    assert [s.title for s in slides] == ["Revenue Overview", "Regional Breakdown"]
    assert slides[0].body == ["Q1 grew 12%", "Q2 grew 8%"]
    assert slides[1].index == 1


def test_read_pptx_slides_numeric_order_beyond_ten(pptx_factory):
    # slide2 vs slide10 must sort numerically, not lexicographically.
    path = pptx_factory([[f"Slide {i}"] for i in range(1, 12)])
    slides = read_pptx_slides(path)
    assert [s.title for s in slides] == [f"Slide {i}" for i in range(1, 12)]


def test_read_pptx_slides_missing_file_returns_empty(tmp_path):
    assert read_pptx_slides(tmp_path / "nope.pptx") == []


def _deck_case(pptx_path):
    return make_case(metadata={"artifacts": [artifact("deck.pptx", str(pptx_path))]})


def test_extract_deck_slides_reads_artifact(pptx_factory):
    path = pptx_factory([["Title A", "body"], ["Title B"]])
    slides = extract_deck_slides(_deck_case(path))
    assert [s.title for s in slides] == ["Title A", "Title B"]


def test_slide_title_quality_skips_without_deck():
    metric = SlideTitleQualityMetric()
    asyncio.run(metric.a_measure(make_case(metadata={})))
    assert metric.skipped is True
    assert metric._geval is None


def test_slide_spec_compliance_uses_deck_slides_fallback(pptx_factory):
    # No deck_metadata in observations — count/titles come from the .pptx.
    path = pptx_factory([["Intro"], ["Method"], ["Results"]])
    metric = SlideSpecComplianceMetric()

    class _Fake:
        score, reason, evaluation_cost = 1.0, "ok", 0.0
        input_tokens = output_tokens = 0

        async def a_measure(self, tc, *args, **kwargs):
            self.tc = tc
            return 1.0

    metric._geval = _Fake()
    asyncio.run(metric.a_measure(_deck_case(path)))
    assert metric.skipped is False  # deck was extractable via fallback
    assert "3" in metric._geval.tc.context[0]  # slide count surfaced to judge


def test_cross_slide_flow_includes_body_from_deck(pptx_factory):
    path = pptx_factory([["Problem", "costs rose"], ["Solution", "automate step"]])
    metric = CrossSlideLogicalFlowMetric()

    class _Fake:
        score, reason, evaluation_cost = 1.0, "ok", 0.0
        input_tokens = output_tokens = 0

        async def a_measure(self, tc, *args, **kwargs):
            self.tc = tc
            return 1.0

    metric._geval = _Fake()
    asyncio.run(metric.a_measure(_deck_case(path)))
    ctx = metric._geval.tc.context[0]
    assert "Problem" in ctx and "automate step" in ctx  # title + body both present
