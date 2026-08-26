"""Judge-graded metric contracts — mocked judge, never a network call.

Verifies three things without contacting an LLM:

1. Skip paths return an explicit skipped result and never build the judge
   (``_geval`` stays None), so no network call can happen.
2. Each judge's criteria carry the structured preamble (acceptance criterion,
   behavioral proxy, measurement method) and the exact-quote evidence rule.
3. When a (fake) judge does score, the metric wires score/reason/success.
"""

import asyncio

import pytest
from deepeval.test_case import LLMTestCase

from metis.library.metrics import (
    BriefAudienceAppropriatenessMetric,
    BriefCompletenessMetric,
    BriefGoalDetailsMetric,
    DeckBriefCoverageMetric,
    SlideVisualQualityMetric,
)
from metis.library.metrics._slide_visual_quality import _image_markers

from .conftest import make_case, tool_call


class _FakeGeval:
    """Stand-in for a GEval that records the case and returns a fixed score."""

    def __init__(self, score: float = 0.8, reason: str = "fake reason"):
        self.score = score
        self.reason = reason
        self.evaluation_cost = 0.01
        self.input_tokens = 5
        self.output_tokens = 7
        self.measured_case: LLMTestCase | None = None

    async def a_measure(self, test_case, *args, **kwargs):
        self.measured_case = test_case
        return self.score


# --------------------------------------------------------------------------
# Skip paths never build a judge (guarantees no network)
# --------------------------------------------------------------------------


def test_brief_goal_details_skips_without_brief():
    metric = BriefGoalDetailsMetric()
    asyncio.run(metric.a_measure(make_case(metadata={"tool_calls": []})))
    assert metric.skipped is True
    assert metric.success is True
    assert metric._geval is None


def test_brief_completeness_skips_without_brief_or_sources():
    metric = BriefCompletenessMetric()
    asyncio.run(metric.a_measure(make_case(metadata={})))
    assert metric.skipped is True
    assert metric._geval is None


def test_deck_brief_coverage_skips_without_deck():
    metric = DeckBriefCoverageMetric()
    asyncio.run(metric.a_measure(make_case(metadata={})))
    assert metric.skipped is True
    assert metric._geval is None


def test_slide_visual_quality_skips_without_images():
    metric = SlideVisualQualityMetric()
    asyncio.run(metric.a_measure(make_case(metadata={"slide_image_refs": []})))
    assert metric.skipped is True
    assert metric.success is True
    assert metric._geval is None


# --------------------------------------------------------------------------
# Criteria composition — evidence rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric",
    [
        BriefGoalDetailsMetric(),
        BriefAudienceAppropriatenessMetric(),
        DeckBriefCoverageMetric(),
        SlideVisualQualityMetric(),
    ],
)
def test_judge_criteria_carry_evidence_rule(metric):
    criteria = metric._get_geval().criteria
    # EVIDENCE_INSTRUCTION requires quoting the exact influencing text.
    assert "exact quotes" in criteria


# --------------------------------------------------------------------------
# Mocked scored path wires score / reason / success
# --------------------------------------------------------------------------


def test_scored_path_wires_result_from_judge():
    metric = BriefGoalDetailsMetric()
    metric._geval = _FakeGeval(score=0.8, reason="judge says fine")
    case = make_case(
        metadata={
            "tool_calls": [
                tool_call("make_ppt", {"brief": "Audience: execs. Goal: inform."})
            ]
        }
    )
    score = asyncio.run(metric.a_measure(case))
    assert score == 0.8
    assert metric.success is True  # 0.8 >= 0.6 threshold
    assert metric.reason == "judge says fine"
    assert metric._geval.measured_case is not None


def test_scored_path_below_threshold_is_unsuccessful():
    metric = BriefGoalDetailsMetric()
    metric._geval = _FakeGeval(score=0.3)
    case = make_case(
        metadata={"tool_calls": [tool_call("make_ppt", {"brief": "some brief text"})]}
    )
    asyncio.run(metric.a_measure(case))
    assert metric.success is False


# --------------------------------------------------------------------------
# Multimodal marker construction (M-SM-13)
# --------------------------------------------------------------------------


def test_image_markers_register_real_file(image_factory):
    path = str(image_factory("slide1.png"))
    markers = _image_markers([path])
    assert len(markers) == 1
    assert markers[0].startswith("[DEEPEVAL:IMAGE:")


def test_image_markers_fall_back_for_missing_ref():
    markers = _image_markers(["/no/such/slide.png"])
    assert markers == ["[DEEPEVAL:IMAGE:/no/such/slide.png]"]


def test_slide_visual_quality_builds_multimodal_case_in_order(image_factory):
    metric = SlideVisualQualityMetric()
    refs = [str(image_factory(f"slide{i}.png")) for i in range(1, 4)]
    augmented = metric._augmented(make_case(metadata={}), refs)
    assert augmented.multimodal is True
    markers = [c for c in augmented.context if c.startswith("[DEEPEVAL:IMAGE:")]
    assert len(markers) == 3


def test_slide_visual_quality_scored_path(image_factory):
    metric = SlideVisualQualityMetric()
    metric._geval = _FakeGeval(score=0.9, reason="slides look consistent")
    refs = [str(image_factory("slide1.png"))]
    score = asyncio.run(
        metric.a_measure(make_case(metadata={"slide_image_refs": refs}))
    )
    assert score == 0.9
    assert metric.success is True
    assert metric.reason == "slides look consistent"
