"""Judge-graded grader contracts — mocked judge, never a network call.

Verifies three things without contacting an LLM:

1. Skip paths return an explicit skipped result and never build the judge
   (``_geval`` stays None), so no network call can happen.
2. Each judge's criteria carry the structured preamble (acceptance criterion,
   behavioral proxy, measurement method) and the exact-quote evidence rule.
3. When a (fake) judge does score, the grader wires score/reason/success.
"""

import asyncio

import pytest
from deepeval.test_case import LLMTestCase

from metis.library.graders import (
    BriefAudienceAppropriatenessGrader,
    BriefCompletenessGrader,
    BriefGoalDetailsGrader,
    DeckBriefCoverageGrader,
    SlideVisualQualityGrader,
)
from metis.library.graders._slide_visual_quality import _image_markers

from .conftest import artifact, make_case, tool_call


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
    grader = BriefGoalDetailsGrader()
    asyncio.run(grader.a_measure(make_case(metadata={"tool_calls": []})))
    assert grader.skipped is True
    assert grader.success is True
    assert grader._geval is None


def test_brief_completeness_skips_without_brief_or_sources():
    grader = BriefCompletenessGrader()
    asyncio.run(grader.a_measure(make_case(metadata={})))
    assert grader.skipped is True
    assert grader._geval is None


def test_deck_brief_coverage_skips_without_deck():
    grader = DeckBriefCoverageGrader()
    asyncio.run(grader.a_measure(make_case(metadata={})))
    assert grader.skipped is True
    assert grader._geval is None


def test_slide_visual_quality_skips_without_images():
    grader = SlideVisualQualityGrader()
    asyncio.run(grader.a_measure(make_case(metadata={})))
    assert grader.skipped is True
    assert grader.success is True
    assert grader._geval is None


# --------------------------------------------------------------------------
# Criteria composition — evidence rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "grader",
    [
        BriefGoalDetailsGrader(),
        BriefAudienceAppropriatenessGrader(),
        DeckBriefCoverageGrader(),
        SlideVisualQualityGrader(),
    ],
)
def test_judge_criteria_carry_evidence_rule(grader):
    criteria = grader._get_geval().criteria
    # EVIDENCE_INSTRUCTION requires quoting the exact influencing text.
    assert "exact quotes" in criteria


# --------------------------------------------------------------------------
# Mocked scored path wires score / reason / success
# --------------------------------------------------------------------------


def test_scored_path_wires_result_from_judge():
    grader = BriefGoalDetailsGrader()
    grader._geval = _FakeGeval(score=0.8, reason="judge says fine")
    case = make_case(
        metadata={
            "tool_calls": [
                tool_call("make_ppt", {"brief": "Audience: execs. Goal: inform."})
            ]
        }
    )
    score = asyncio.run(grader.a_measure(case))
    assert score == 0.8
    assert grader.success is True  # 0.8 >= 0.6 threshold
    assert grader.reason == "judge says fine"
    assert grader._geval.measured_case is not None


def test_scored_path_below_threshold_is_unsuccessful():
    grader = BriefGoalDetailsGrader()
    grader._geval = _FakeGeval(score=0.3)
    case = make_case(
        metadata={"tool_calls": [tool_call("make_ppt", {"brief": "some brief text"})]}
    )
    asyncio.run(grader.a_measure(case))
    assert grader.success is False


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
    grader = SlideVisualQualityGrader()
    refs = [str(image_factory(f"slide{i}.png")) for i in range(1, 4)]
    augmented = grader._augmented(make_case(metadata={}), refs)
    assert augmented.multimodal is True
    markers = [c for c in augmented.context if c.startswith("[DEEPEVAL:IMAGE:")]
    assert len(markers) == 3


def test_slide_visual_quality_scored_path(pdf_factory):
    grader = SlideVisualQualityGrader()
    grader._geval = _FakeGeval(score=0.9, reason="slides look consistent")
    pdf_path = str(pdf_factory("deck.pdf"))
    case = make_case(
        metadata={
            "turn_index": 0,
            "artifacts": [artifact("deck.pdf", pdf_path, at_turn=0)],
        }
    )
    score = asyncio.run(grader.a_measure(case))
    assert score == 0.9
    assert grader.success is True
    assert grader.reason == "slides look consistent"
