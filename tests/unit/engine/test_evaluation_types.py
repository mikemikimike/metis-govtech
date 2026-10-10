"""Tests for GraderResult and TurnResult dataclasses."""

from deepeval.test_case import LLMTestCase

from metis.engine.evaluation.types import GraderResult, TurnResult


def test_grader_result_defaults():
    mr = GraderResult(
        name="Test", score=0.8, reason="good", success=True, skipped=False
    )
    assert mr.evaluation_cost is None
    assert mr.input_tokens is None
    assert mr.output_tokens is None


def test_grader_result_with_cost():
    mr = GraderResult(
        name="Test",
        score=0.8,
        reason="good",
        success=True,
        skipped=False,
        evaluation_cost=0.01,
        input_tokens=100,
        output_tokens=50,
    )
    assert mr.evaluation_cost == 0.01
    assert mr.input_tokens == 100


def test_test_case_result():
    tc = LLMTestCase(input="hello", actual_output="world")
    mr = GraderResult(name="M", score=1.0, reason="", success=True, skipped=False)
    tcr = TurnResult(llm_test_case=tc, grader_results=[mr])
    assert len(tcr.grader_results) == 1
    assert tcr.llm_test_case.input == "hello"
