"""
Visualization and persistence of eval results.

Produces:
1. Terminal summary table (always)
2. JSON results file (machine-readable, for notebooks/scripts)
3. HTML report (open in browser for visual inspection)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from metis.core.console import console
from metis.engine.evaluation.types import EvalResult
from metis.engine.extractor.types import (
    RoutingSummary,
    SessionMetricsEntry,
)

from ._aggregation import aggregate_metrics
from ._html_sections import (
    render_metric_table,
    render_routing_section,
    render_summary_cards,
    render_task_sections,
    render_trace_details,
)
from ._styles import REPORT_CSS


class PersonaContext(TypedDict, total=False):
    id: str
    description: str
    stop_reason: str
    total_turns: int
    duration_seconds: float


class TaskContext(TypedDict, total=False):
    description: str
    persona_id: str
    persona_description: str
    fixtures: list[str]
    stop_reason: str
    total_turns: int
    duration_seconds: float
    personas: list[PersonaContext]


RESULTS_DIR = Path.cwd() / "results"


@dataclass
class ReportResult:
    """Result of report generation.

    :param json_path: Path to the JSON results file.
    :param html_path: Path to the HTML report file.
    :param terminal_summary: The terminal summary string.
    """

    json_path: Path
    html_path: Path
    terminal_summary: str


def format_terminal_summary(
    test_results: list[dict],
    run_id: str,
    routing_summary: RoutingSummary | None = None,
    session_metrics: list[SessionMetricsEntry] | None = None,
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

    metric_agg = aggregate_metrics(test_results, session_metrics)

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


def save_json_results(
    test_results: list[dict],
    run_id: str,
    routing_summary: RoutingSummary | None = None,
    session_metrics: list[SessionMetricsEntry] | None = None,
    timings: dict | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Save detailed results as JSON for programmatic access."""
    target_dir = output_dir or RESULTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / f"{run_id}.json"

    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    for tc in test_results:
        for m in tc["metrics"]:
            total_cost += m.get("cost") or 0
            total_input_tokens += m.get("input_tokens") or 0
            total_output_tokens += m.get("output_tokens") or 0

    total_latency = sum((timings or {}).values())
    metric_agg = aggregate_metrics(test_results, session_metrics)

    summary = {
        name: {
            "pass": agg["pass_count"],
            "fail": agg["fail"],
            "skip": agg["skip"],
            "scores": agg["scores"],
            "pass_rate": agg["pass_rate"],
            "avg_score": agg["avg_score"],
        }
        for name, agg in metric_agg.items()
    }

    output = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "cost": {
            "total_usd": round(total_cost, 6) if total_cost else None,
            "input_tokens": total_input_tokens or None,
            "output_tokens": total_output_tokens or None,
        },
        "latency_seconds": round(total_latency, 1),
        "timings": timings or {},
        "routing": routing_summary or {},
        "summary": summary,
        "session_metrics": session_metrics or [],
        "test_cases": test_results,
    }
    with open(filepath, "w") as f:
        json.dump(output, f, indent=2, default=str)
    return filepath


def save_html_report(
    test_results: list[dict],
    run_id: str,
    routing_summary: RoutingSummary | None = None,
    session_metrics: list[SessionMetricsEntry] | None = None,
    timings: dict | None = None,
    output_dir: Path | None = None,
    experiment_description: str | None = None,
    task_contexts: dict[str, TaskContext] | None = None,
) -> Path:
    """Generate a self-contained HTML report."""
    target_dir = output_dir or RESULTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / f"{run_id}.html"

    metric_agg = aggregate_metrics(test_results, session_metrics)

    total_cost = sum(m.get("cost") or 0 for tc in test_results for m in tc["metrics"])
    total_latency = sum((timings or {}).values())

    html = _render_html(
        run_id,
        metric_agg,
        test_results,
        routing_summary,
        total_cost,
        total_latency,
        experiment_description=experiment_description,
        task_contexts=task_contexts,
    )
    with open(filepath, "w") as f:
        f.write(html)
    return filepath


def generate_report(
    eval_result: EvalResult,
    *,
    run_id: str | None = None,
    output_dir: Path | None = None,
    experiment_description: str | None = None,
    task_contexts: dict[str, TaskContext] | None = None,
) -> ReportResult:
    """Generate terminal summary, JSON results, and HTML report.

    :param eval_result: Output of :func:`metis.engine.evaluation.evaluate`.
    :param run_id: Custom run identifier (auto-generated if None).
    :returns: :class:`ReportResult` with paths to generated files.

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

    test_results = _convert_eval_result(eval_result)

    terminal_summary = format_terminal_summary(
        test_results,
        run_id,
        eval_result.routing_summary,
        eval_result.session_metrics,
    )
    console.print(terminal_summary)

    json_path = save_json_results(
        test_results,
        run_id,
        eval_result.routing_summary,
        eval_result.session_metrics,
        eval_result.timings,
        output_dir=output_dir,
    )
    console.print(f"  JSON results: {json_path}")

    html_path = save_html_report(
        test_results,
        run_id,
        eval_result.routing_summary,
        eval_result.session_metrics,
        eval_result.timings,
        output_dir=output_dir,
        experiment_description=experiment_description,
        task_contexts=task_contexts,
    )
    console.print(f"  HTML report:  {html_path}")
    console.print(f"  Open with:    open {html_path}\n")

    return ReportResult(
        json_path=json_path,
        html_path=html_path,
        terminal_summary=terminal_summary,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _convert_eval_result(eval_result: EvalResult) -> list[dict]:
    """Convert EvalResult into the dict-based format used by report internals."""
    test_results = []
    for tcr in eval_result.test_results:
        tc = tcr.test_case
        metadata = tc.metadata or {}
        trace_id = metadata.get("trace_id", "unknown")
        metrics_data = []
        for mr in tcr.metrics:
            metric_entry = {
                "name": mr.name,
                "score": mr.score,
                "reason": mr.reason,
                "success": mr.success,
                "skipped": mr.skipped,
            }
            if mr.evaluation_cost is not None:
                metric_entry["cost"] = mr.evaluation_cost
            if mr.input_tokens is not None:
                metric_entry["input_tokens"] = mr.input_tokens
            if mr.output_tokens is not None:
                metric_entry["output_tokens"] = mr.output_tokens
            metrics_data.append(metric_entry)
        test_results.append(
            {
                "trace_id": trace_id,
                "session_id": metadata.get("session_id", ""),
                "scenario_id": metadata.get("scenario_id", ""),
                "turn_index": metadata.get("turn_index", 0),
                "total_turns": metadata.get("total_turns", 1),
                "input": tc.input or "",
                "output": tc.actual_output or "",
                "routed_to": eval_result.trace_routing.get(trace_id, "direct"),
                "metrics": metrics_data,
            }
        )
    return test_results


def _render_html(
    run_id: str,
    metric_agg: dict,
    test_results: list[dict],
    routing_summary: RoutingSummary | None = None,
    total_cost: float = 0,
    total_latency: float = 0,
    experiment_description: str | None = None,
    task_contexts: dict[str, TaskContext] | None = None,
) -> str:
    """Compose the full HTML page from section fragments."""
    import html as html_mod

    description_html = (
        f'<p class="description">{html_mod.escape(experiment_description)}</p>'
        if experiment_description
        else ""
    )

    total_pass = sum(a["pass_count"] for a in metric_agg.values())
    total_fail = sum(a["fail"] for a in metric_agg.values())
    total_skip = sum(a["skip"] for a in metric_agg.values())
    evaluated = total_pass + total_fail
    overall_rate = total_pass / evaluated * 100 if evaluated else 0

    summary_cards = render_summary_cards(
        num_traces=len(test_results),
        num_metrics=len(metric_agg),
        overall_rate=overall_rate,
        total_fail=total_fail,
        total_skip=total_skip,
        total_latency=total_latency,
        total_cost=total_cost,
    )
    routing_html = render_routing_section(routing_summary)
    tasks_html = render_task_sections(test_results, task_contexts)
    metric_table_html = render_metric_table(metric_agg)
    trace_details_html = render_trace_details(test_results)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Orca Eval Report — {run_id}</title>
    <style>
        {REPORT_CSS}
    </style>
</head>
<body>
    <h1>Orca Eval Report</h1>
    {description_html}
    <p class="subtitle">Run: {run_id} &middot; {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

    {summary_cards}
    {routing_html}
    {tasks_html}

    {metric_table_html}

    {trace_details_html}
</body>
</html>"""
