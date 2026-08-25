"""
Visualization and persistence of eval results.

Produces:
1. A terminal summary table.
2. The product evaluation report, as an HTML page and as JSON data.

The report joins each metric result onto the product profile that asked for it, so a
reader sees which behaviour is weak, and which persona or scenario is hard to test,
rather than only which metric failed. Every number comes from a file the run already
wrote; no model writes any of its text. A run with no product profile writes no report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from metis.core.console import console
from metis.core.logging import get_logger
from metis.engine.evaluation.types import EvalDurations, EvalResult, SessionResult
from metis.engine.extractor.types import RoutingSummary
from metis.engine.reporting._types import (
    SessionMetricResult,
    SessionReport,
    TurnMetricResult,
    TurnReport,
)

from ._aggregation import aggregate_metrics
from ._report import build_report, load_report_sources
from ._report_page import render_report_page

logger = get_logger(__name__)


RESULTS_DIR = Path.cwd() / "results"


@dataclass
class ReportResult:
    """Result of report generation.

    :param json_path: Path to the report data, or `None` when no report was written.
    :param html_path: Path to the report page, or `None` when no report was written.
    :param terminal_summary: The terminal summary string.
    """

    json_path: Path | None
    html_path: Path | None
    terminal_summary: str


def format_terminal_summary(
    turn_results: list[TurnReport],
    run_id: str,
    routing_summary: RoutingSummary | None = None,
    session_results: list[SessionReport] | None = None,
) -> str:
    """Print a compact terminal summary of all metric results."""
    lines = []
    lines.append(f"\n{'=' * 70}")
    lines.append(f"  EVAL RUN: {run_id}")
    lines.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"{'=' * 70}\n")

    if routing_summary:
        lines.append("  TRACE ROUTING")
        lines.append(f"  {'-' * 40}")
        lines.append(f"  Sessions:            {routing_summary['total_sessions']}")
        lines.append(f"  Total traces:        {routing_summary['total_traces']}")
        lines.append(f"  Direct handle:       {routing_summary['direct_handle']}")
        lines.append(f"  Routing failed:      {routing_summary['routing_failed']}")
        for agent, count in sorted(routing_summary["subagent_counts"].items()):
            lines.append(f"  -> {agent:<20} {count}")
        lines.append("")

    metric_agg = aggregate_metrics(turn_results, session_results)

    lines.append(f"  {'Metric':<40} {'Pass':>6} {'Fail':>6} {'Skip':>6} {'Rate':>7}")
    lines.append(f"  {'-' * 40} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 7}")

    for name, agg in sorted(metric_agg.items()):
        evaluated = agg["pass_count"] + agg["fail"]
        rate = agg["pass_count"] / evaluated if evaluated > 0 else 0
        marker = " " if agg["fail"] == 0 else "!"
        rate_str = f"{rate * 100:.1f}%" if evaluated > 0 else "  N/A"
        lines.append(
            f" {marker}{name:<40} {agg['pass_count']:>6} {agg['fail']:>6} {agg['skip']:>6} {rate_str:>7}"
        )

    total_pass = sum(a["pass_count"] for a in metric_agg.values())
    total_fail = sum(a["fail"] for a in metric_agg.values())
    total_skip = sum(a["skip"] for a in metric_agg.values())
    evaluated = total_pass + total_fail
    lines.append(
        f"\n  {'TOTAL':<40} {total_pass:>6} {total_fail:>6} "
        f"{total_skip:>6} {total_pass / evaluated * 100 if evaluated else 0:>6.1f}%"
    )
    if total_skip:
        lines.append(f"  ({total_skip} skipped — excluded from pass rate)")

    lines.append(f"\n{'=' * 70}\n")
    return "\n".join(lines)


def save_report(
    turn_results: list[TurnReport],
    run_id: str,
    routing_summary: RoutingSummary | None = None,
    session_results: list[SessionReport] | None = None,
    durations: EvalDurations | None = None,
    output_dir: Path | None = None,
) -> tuple[Path, Path] | None:
    """Write the product evaluation report, as a page and as data.

    The report needs the product profile the run was planned against. `simulate` freezes
    its whole input directory beside the results, so the profile is one level up from the
    report directory. A run with no profile gets no report, and that is not an error.

    :returns: The HTML path and the JSON path, or `None` when there is no profile.
    """
    target_dir = output_dir or RESULTS_DIR
    run_dir = target_dir.parent

    sources = load_report_sources(run_dir)
    if sources is None:
        return None
    profile, experiment, persona_of, trial_outcomes = sources

    d = durations or EvalDurations()
    timings = {
        "turn_metrics_seconds": d.turn_metrics_seconds,
        "session_metrics_seconds": d.session_metrics_seconds,
    }
    latency = round(d.turn_metrics_seconds + d.session_metrics_seconds, 1) or None

    report = build_report(
        profile,
        experiment,
        turn_results,
        persona_of=persona_of,
        session_metrics=session_results,
        run_id=run_id,
        timestamp=datetime.now().isoformat(),
        latency_seconds=latency,
        timings=timings,
        routing=dict(routing_summary or {}),
        trial_outcomes=trial_outcomes,
    )

    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{run_id}.json"
    html_path = target_dir / f"{run_id}.html"
    json_path.write_text(json.dumps(report, indent=1, default=str) + "\n")
    html_path.write_text(render_report_page(report, title=report["product"]))

    logger.info(
        "report_written",
        tasks=len(report["tasks"]),
        behaviours=len(report["behaviours"]),
        criteria=len(report["criteria"]),
        scored=sum(1 for c in report["criteria"].values() if c["rate"] is not None),
        unresolved=len(report["unresolved"]),
    )
    return html_path, json_path


def generate_report(
    eval_result: EvalResult,
    *,
    run_id: str | None = None,
    output_dir: Path | None = None,
) -> ReportResult:
    """Print the terminal summary and write the product evaluation report.

    :param eval_result: Output of :func:`metis.engine.evaluation.evaluate`.
    :param run_id: Custom run identifier (auto-generated if None).
    :returns: :class:`ReportResult` with paths to the written files.

    Example::

        from metis.core.console import console
        from metis.engine import evaluate, generate_report
        from metis.engine.extractor import fetch_by_session_id, get_langfuse_client

        lf = get_langfuse_client()
        fetch_result = fetch_by_session_id(session_id, lf)
        eval_result = evaluate(fetch_result, metric_refs)
        report_result = generate_report(eval_result, run_id="my-run-001")
        console.print(report_result.html_path)
    """
    if run_id is None:
        run_id = f"langfuse-eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    turn_results: list[TurnReport] = _convert_turn_results(eval_result)
    session_results: list[SessionReport] = _convert_session_results(
        eval_result.session_results
    )

    terminal_summary = format_terminal_summary(
        turn_results,
        run_id,
        eval_result.routing_summary,
        session_results,
    )
    console.print(terminal_summary)

    html_path: Path | None = None
    json_path: Path | None = None
    try:
        paths = save_report(
            turn_results,
            run_id,
            eval_result.routing_summary,
            session_results,
            eval_result.durations,
            output_dir=output_dir,
        )
    except Exception as exc:  # noqa: BLE001 - a report error must not fail evaluation
        logger.warning("report_failed", error=str(exc), error_type=type(exc).__name__)
        console.print(f"  Report:       not written ({type(exc).__name__})")
    else:
        if paths:
            html_path, json_path = paths
            console.print(f"  JSON results: {json_path}")
            console.print(f"  HTML report:  {html_path}")
            console.print(f"  Open with:    open {html_path}\n")
        else:
            console.print("  Report:       not written (no profile.yaml)")

    return ReportResult(
        json_path=json_path,
        html_path=html_path,
        terminal_summary=terminal_summary,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _convert_turn_results(eval_result: EvalResult) -> list[TurnReport]:
    """Convert turn results into the report-ready format."""
    results: list[TurnReport] = []
    for tcr in eval_result.turn_results:
        tc = tcr.llm_test_case
        metadata = tc.metadata or {}
        trace_id = metadata.get("trace_id", "unknown")
        metrics_data: list[TurnMetricResult] = []
        for mr in tcr.metric_results:
            metric_entry = TurnMetricResult(
                name=mr.name,
                score=mr.score,
                reason=mr.reason,
                success=mr.success,
                skipped=mr.skipped,
            )
            if mr.evaluation_cost is not None:
                metric_entry["cost"] = mr.evaluation_cost
            if mr.input_tokens is not None:
                metric_entry["input_tokens"] = mr.input_tokens
            if mr.output_tokens is not None:
                metric_entry["output_tokens"] = mr.output_tokens
            metrics_data.append(metric_entry)
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
                metrics=metrics_data,
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
        metrics_out: list[SessionMetricResult] = []
        for mr in scr.metric_results:
            metrics_out.append(
                SessionMetricResult(
                    name=mr.name,
                    score=mr.score,
                    reason=mr.reason,
                    success=mr.success,
                    skipped=mr.skipped,
                )
            )
        entries.append(
            SessionReport(
                session_id=sid,
                metrics=metrics_out,
            )
        )
    return entries
