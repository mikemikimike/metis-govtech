"""Convert in-memory evaluation results into the results.json handoff file.

EvalResult holds deepeval test cases, which only this package can import. The
models in metis.core.reporting are their serializable projection, which
`metis insights report` reads to build the product evaluation report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.core.reporting import (
    EvaluationResults,
    SessionGraderResult,
    SessionReport,
    TurnGraderResult,
    TurnReport,
)

if TYPE_CHECKING:
    from metis.engine.evaluation.types import EvalResult, SessionResult


def to_evaluation_results(eval_result: EvalResult, *, run_id: str) -> EvaluationResults:
    """Project a merged EvalResult onto the results.json model."""
    d = eval_result.durations
    return EvaluationResults(
        run_id=run_id,
        turn_results=_convert_turn_results(eval_result),
        session_results=_convert_session_results(eval_result.session_results),
        routing=dict(eval_result.routing_summary),
        timings={
            "turn_graders_seconds": d.turn_graders_seconds,
            "session_graders_seconds": d.session_graders_seconds,
        },
        latency_seconds=round(d.turn_graders_seconds + d.session_graders_seconds, 1)
        or None,
    )


def _convert_turn_results(eval_result: EvalResult) -> list[TurnReport]:
    """Convert turn results into the report-ready format."""
    results: list[TurnReport] = []
    for tcr in eval_result.turn_results:
        tc = tcr.llm_test_case
        metadata = tc.metadata or {}
        trace_id = metadata.get("trace_id", "unknown")
        graders_data: list[TurnGraderResult] = []
        for mr in tcr.grader_results:
            graders_data.append(
                TurnGraderResult(
                    criterion_id=mr.criterion_id,
                    grader_fqn=mr.grader_fqn,
                    grader_args=mr.grader_args,
                    task_id=mr.task_id,
                    trial_index=mr.trial_index,
                    name=mr.name,
                    score=mr.score,
                    reason=mr.reason,
                    success=mr.success,
                    skipped=mr.skipped,
                    cost=mr.evaluation_cost,
                    input_tokens=mr.input_tokens,
                    output_tokens=mr.output_tokens,
                )
            )
        delegation = metadata.get("delegation") or {}
        routed_to = delegation.get("target", "") if isinstance(delegation, dict) else ""
        results.append(
            TurnReport(
                trace_id=trace_id,
                session_id=metadata.get("session_id", ""),
                scenario_id=metadata.get("scenario_id", ""),
                turn_index=metadata.get("turn_index", 0),
                total_turns=metadata.get("total_turns", 1),
                input=tc.input or "",
                output=tc.actual_output or "",
                routed_to=routed_to or "direct",
                graders=graders_data,
            )
        )
    return results


def _convert_session_results(
    session_results: list[SessionResult],
) -> list[SessionReport]:
    """Convert session results into the report-ready format."""
    entries: list[SessionReport] = []
    for scr in session_results:
        ctc = scr.conversational_test_case
        sid = (ctc.metadata or {}).get("session_id", "unknown")
        graders_out: list[SessionGraderResult] = []
        for mr in scr.grader_results:
            graders_out.append(
                SessionGraderResult(
                    criterion_id=mr.criterion_id,
                    grader_fqn=mr.grader_fqn,
                    grader_args=mr.grader_args,
                    task_id=mr.task_id,
                    trial_index=mr.trial_index,
                    name=mr.name,
                    score=mr.score,
                    reason=mr.reason,
                    success=mr.success,
                    skipped=mr.skipped,
                )
            )
        entries.append(SessionReport(session_id=sid, graders=graders_out))
    return entries
