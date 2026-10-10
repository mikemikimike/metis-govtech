"""EvalResult (in memory, holds deepeval objects) → EvaluationResults (results.json)."""

from __future__ import annotations

from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase, Turn

from metis.engine.evaluation.results import to_evaluation_results
from metis.engine.evaluation.types import (
    EvalDurations,
    EvalResult,
    GraderResult,
    SessionResult,
    TurnResult,
)
from metis.engine.extractor.types import RoutingSummary


def _grader(name: str, **overrides: object) -> GraderResult:
    fields: dict = {
        "name": name,
        "score": 1.0,
        "reason": "ok",
        "success": True,
        "skipped": False,
    }
    fields.update(overrides)
    return GraderResult(**fields)


def _eval_result(durations: EvalDurations) -> EvalResult:
    delegated = LLMTestCase(
        input="hi",
        actual_output="hello",
        metadata={
            "trace_id": "t-1",
            "session_id": "s-1",
            "scenario_id": "task-1",
            "turn_index": 1,
            "total_turns": 2,
            "delegation": {"target": "analyst"},
        },
    )
    bare = LLMTestCase(input="q", actual_output="a")
    session = ConversationalTestCase(
        turns=[Turn(role="user", content="hi")], metadata={"session_id": "s-1"}
    )
    return EvalResult(
        turn_results=[
            TurnResult(
                llm_test_case=delegated,
                grader_results=[
                    _grader(
                        "Routing Accuracy",
                        criterion_id="AC-1",
                        grader_fqn="metis.library.graders.RoutingAccuracyGrader",
                        grader_args={"k": 1},
                        task_id="TC-001",
                        trial_index=2,
                        evaluation_cost=0.01,
                        input_tokens=10,
                        output_tokens=3,
                    )
                ],
            ),
            TurnResult(llm_test_case=bare, grader_results=[_grader("Turn Budget")]),
        ],
        session_results=[
            SessionResult(
                conversational_test_case=session,
                grader_results=[_grader("Session Efficiency", score=0.5)],
            )
        ],
        routing_summary=RoutingSummary(
            total_traces=2,
            total_sessions=1,
            direct_handle=1,
            routing_failed=0,
            subagent_counts={"analyst": 1},
        ),
        durations=durations,
    )


def test_turn_results_carry_trace_metadata_and_grader_identity() -> None:
    results = to_evaluation_results(
        _eval_result(EvalDurations(1.24, 0.5)), run_id="report"
    )

    first, second = results.turn_results
    assert (first.trace_id, first.session_id, first.scenario_id) == (
        "t-1",
        "s-1",
        "task-1",
    )
    assert (first.turn_index, first.total_turns) == (1, 2)
    assert first.routed_to == "analyst"
    grader = first.graders[0]
    assert grader.criterion_id == "AC-1"
    assert grader.grader_fqn == "metis.library.graders.RoutingAccuracyGrader"
    assert grader.grader_args == {"k": 1}
    assert (grader.task_id, grader.trial_index) == ("TC-001", 2)
    assert (grader.cost, grader.input_tokens, grader.output_tokens) == (0.01, 10, 3)
    # A turn without metadata keeps the defaults the old report path used.
    assert second.trace_id == "unknown"
    assert second.routed_to == "direct"
    assert (second.turn_index, second.total_turns) == (0, 1)


def test_session_results_routing_timings_and_latency() -> None:
    results = to_evaluation_results(
        _eval_result(EvalDurations(1.24, 0.5)), run_id="report"
    )

    assert results.run_id == "report"
    assert results.session_results[0].session_id == "s-1"
    assert results.session_results[0].graders[0].score == 0.5
    assert results.routing["subagent_counts"] == {"analyst": 1}
    assert results.timings == {
        "turn_graders_seconds": 1.24,
        "session_graders_seconds": 0.5,
    }
    assert results.latency_seconds == 1.7


def test_zero_durations_give_no_latency() -> None:
    results = to_evaluation_results(_eval_result(EvalDurations()), run_id="report")
    assert results.latency_seconds is None
