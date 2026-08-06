"""
Visualization and persistence of eval results.

Produces:
1. Terminal summary table (always)
2. JSON results file (machine-readable, for notebooks/scripts)
3. HTML report (open in browser for visual inspection)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from metis.core.console import console
from metis.engine.evaluation.types import EvalResult
from metis.engine.extractor.types import (
    RoutingSummary,
    SessionMetricsEntry,
)

class TaskContext(TypedDict, total=False):
    description: str
    persona_id: str
    persona_description: str
    fixtures: list[str]
    stop_reason: str
    total_turns: int
    duration_seconds: float


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


def ensure_results_dir():
    RESULTS_DIR.mkdir(exist_ok=True)


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

    # Routing breakdown
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

    # Aggregate by metric
    metric_agg: dict[str, dict] = {}
    for result in test_results:
        for metric in result["metrics"]:
            name = metric["name"]
            if name not in metric_agg:
                metric_agg[name] = {
                    "pass": 0,
                    "fail": 0,
                    "skip": 0,
                    "scores": [],
                }
            if metric.get("skipped"):
                metric_agg[name]["skip"] += 1
            elif metric["success"]:
                metric_agg[name]["pass"] += 1
            else:
                metric_agg[name]["fail"] += 1
            metric_agg[name]["scores"].append(metric["score"])

    lines.append(f"  {'Metric':<40} {'Pass':>6} {'Fail':>6} {'Skip':>6} {'Rate':>7}")
    lines.append(f"  {'-' * 40} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 7}")

    for name, agg in sorted(metric_agg.items()):
        evaluated = agg["pass"] + agg["fail"]
        rate = agg["pass"] / evaluated if evaluated > 0 else 0
        marker = " " if agg["fail"] == 0 else "!"
        rate_str = f"{rate * 100:.1f}%" if evaluated > 0 else "  N/A"
        lines.append(
            f" {marker}{name:<40} {agg['pass']:>6} {agg['fail']:>6} {agg['skip']:>6} {rate_str:>7}"
        )

    # Merge session-level metrics into the same aggregate
    if session_metrics:
        for sess in session_metrics:
            for m in sess["metrics"]:
                name = m["name"]
                if name not in metric_agg:
                    metric_agg[name] = {
                        "pass": 0,
                        "fail": 0,
                        "skip": 0,
                        "scores": [],
                    }
                if m.get("skipped"):
                    metric_agg[name]["skip"] += 1
                elif m["success"]:
                    metric_agg[name]["pass"] += 1
                else:
                    metric_agg[name]["fail"] += 1
                metric_agg[name]["scores"].append(m["score"])

    total_pass = sum(a["pass"] for a in metric_agg.values())
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

    # Compute total cost from all metrics (when available)
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    for tc in test_results:
        for m in tc["metrics"]:
            total_cost += m.get("cost") or 0
            total_input_tokens += m.get("input_tokens") or 0
            total_output_tokens += m.get("output_tokens") or 0

    total_latency = sum((timings or {}).values())

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
        "summary": _build_summary(test_results),
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

    metric_agg = _build_summary(test_results)
    # Merge session metrics into the same summary
    if session_metrics:
        for sess in session_metrics:
            for m in sess.get("metrics", []):
                name = m["name"]
                if name not in metric_agg:
                    metric_agg[name] = {
                        "pass": 0,
                        "fail": 0,
                        "skip": 0,
                        "scores": [],
                        "pass_rate": 0,
                        "avg_score": 0,
                    }
                if m.get("skipped"):
                    metric_agg[name]["skip"] += 1
                elif m["success"]:
                    metric_agg[name]["pass"] += 1
                else:
                    metric_agg[name]["fail"] += 1
                metric_agg[name]["scores"].append(m["score"])
        for agg in metric_agg.values():
            ev = agg["pass"] + agg["fail"]
            agg["pass_rate"] = agg["pass"] / ev if ev > 0 else 0

    failures = _extract_failures(test_results)

    # Compute cost for HTML
    total_cost = sum(m.get("cost") or 0 for tc in test_results for m in tc["metrics"])
    total_latency = sum((timings or {}).values())

    html = _render_html(
        run_id,
        metric_agg,
        test_results,
        failures,
        routing_summary,
        session_metrics,
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

    # Convert EvalResult into the dict-based format used by report internals
    test_results = []
    for tc, test_result in zip(
        eval_result.test_cases, eval_result.test_results, strict=False
    ):
        metadata = tc.metadata or {}
        trace_id = metadata.get("trace_id", "unknown")
        metrics_data = []
        for md in test_result.metrics_data:
            skipped = md.reason.endswith("— SKIPPED") if md.reason else False
            metric_entry = {
                "name": md.name,
                "score": md.score,
                "reason": md.reason or "",
                "success": md.success,
                "skipped": skipped,
            }
            cost = getattr(md, "evaluation_cost", None)
            in_tok = getattr(md, "input_tokens", None)
            out_tok = getattr(md, "output_tokens", None)
            if cost is not None:
                metric_entry["cost"] = cost
            if in_tok is not None:
                metric_entry["input_tokens"] = in_tok
            if out_tok is not None:
                metric_entry["output_tokens"] = out_tok
            metrics_data.append(metric_entry)
        test_results.append(
            {
                "trace_id": trace_id,
                "session_id": metadata.get("session_id", ""),
                "task_id": metadata.get("task_id", ""),
                "turn_index": metadata.get("turn_index", 0),
                "total_turns": metadata.get("total_turns", 1),
                "input": tc.input or "",
                "output": tc.actual_output or "",
                "routed_to": eval_result.trace_routing.get(trace_id, "direct"),
                "metrics": metrics_data,
            }
        )

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


def _build_summary(test_results: list[dict]) -> dict:
    metric_agg = {}
    for result in test_results:
        for metric in result["metrics"]:
            name = metric["name"]
            if name not in metric_agg:
                metric_agg[name] = {
                    "pass": 0,
                    "fail": 0,
                    "skip": 0,
                    "scores": [],
                }
            if metric.get("skipped"):
                metric_agg[name]["skip"] += 1
            elif metric["success"]:
                metric_agg[name]["pass"] += 1
            else:
                metric_agg[name]["fail"] += 1
            metric_agg[name]["scores"].append(metric["score"])

    for _name, agg in metric_agg.items():
        evaluated = agg["pass"] + agg["fail"]
        agg["pass_rate"] = agg["pass"] / evaluated if evaluated > 0 else 0
        agg["avg_score"] = (
            sum(agg["scores"]) / len(agg["scores"]) if agg["scores"] else 0
        )

    return metric_agg


def _extract_failures(test_results: list[dict]) -> list[dict]:
    failures = []
    for result in test_results:
        for metric in result["metrics"]:
            if not metric["success"] and not metric.get("skipped"):
                failures.append(
                    {
                        "trace_id": result["trace_id"],
                        "session_id": result.get("session_id", ""),
                        "task_id": result.get("task_id", ""),
                        "turn_index": result.get("turn_index", 0),
                        "total_turns": result.get("total_turns", 1),
                        "routed_to": result.get("routed_to", ""),
                        "input": result["input"],
                        "output": result["output"],
                        "metric": metric["name"],
                        "score": metric["score"],
                        "reason": metric["reason"],
                    }
                )
    return failures


def _render_trace_details(test_results: list[dict], html_mod) -> str:
    """Render per-session trace detail: group traces by session, show full I/O and all metrics."""
    from collections import OrderedDict

    # Group by session
    sessions = OrderedDict()
    for result in test_results:
        sid = result.get("session_id") or result["trace_id"]
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(result)

    html_out = ""
    for session_idx, (sid, traces) in enumerate(sessions.items(), start=1):
        total_turns = len(traces)
        session_pass = sum(
            1
            for t in traces
            for m in t["metrics"]
            if m["success"] and not m.get("skipped")
        )
        session_fail = sum(
            1
            for t in traces
            for m in t["metrics"]
            if not m["success"] and not m.get("skipped")
        )
        session_skip = sum(1 for t in traces for m in t["metrics"] if m.get("skipped"))
        session_color = "#22c55e" if session_fail == 0 else "#ef4444"

        turns_html = ""
        for turn_idx, result in enumerate(traces):
            trace_id = result["trace_id"][:12]
            routed_to = result.get("routed_to", "direct")
            escaped_input = html_mod.escape(result["input"] or "")
            escaped_output = html_mod.escape(result["output"] or "")

            n_pass = sum(
                1 for m in result["metrics"] if m["success"] and not m.get("skipped")
            )
            n_fail = sum(
                1
                for m in result["metrics"]
                if not m["success"] and not m.get("skipped")
            )
            n_skip = sum(1 for m in result["metrics"] if m.get("skipped"))
            turn_color = "#22c55e" if n_fail == 0 else "#ef4444"

            metric_rows = ""
            for m in sorted(
                result["metrics"],
                key=lambda x: (
                    x.get("skipped", False),
                    x["success"],
                    x["score"],
                ),
            ):
                score = m["score"]
                if m.get("skipped"):
                    badge = '<span class="badge badge-skip">SKIP</span>'
                elif m["success"]:
                    badge = f'<span class="badge badge-pass">{score:.2f}</span>'
                else:
                    badge = f'<span class="badge badge-fail">{score:.2f}</span>'

                reason = html_mod.escape(m.get("reason", "") or "")
                metric_rows += f"""
                <div class="trace-metric">
                    <div class="trace-metric-header">
                        {badge}
                        <span class="trace-metric-name">{html_mod.escape(m["name"])}</span>
                    </div>
                    <div class="trace-metric-reason">{reason}</div>
                </div>"""

            turns_html += f"""
            <div class="session-turn">
                <div class="session-turn-header">
                    <span style="color:{turn_color};font-weight:600">Turn {turn_idx + 1}</span>
                    <code>{trace_id}</code>
                    <span class="trace-meta">{routed_to} &middot; {n_pass}P {n_fail}F {n_skip}S</span>
                </div>
                <div class="session-turn-io">
                    <div class="io-block">
                        <div class="context-label">Input</div>
                        <pre>{escaped_input}</pre>
                    </div>
                    <div class="io-block">
                        <div class="context-label">Output</div>
                        <pre>{escaped_output}</pre>
                    </div>
                </div>
                <details class="metrics-dropdown">
                    <summary>Metrics ({n_pass + n_fail + n_skip})</summary>
                    <div class="trace-metrics-list">{metric_rows}</div>
                </details>
            </div>"""

        html_out += f"""
        <details class="trace-card" {"open" if session_fail > 0 else ""}>
            <summary>
                <span style="color:{session_color};font-weight:600">Session {session_idx}</span>
                <code>{sid[:24]}</code>
                <span class="trace-meta">{total_turns} turn(s) &middot; {session_pass}P {session_fail}F {session_skip}S</span>
            </summary>
            <div class="trace-body">{turns_html}</div>
        </details>"""

    return html_out


def _render_html(
    run_id: str,
    metric_agg: dict,
    test_results: list[dict],
    failures: list[dict],
    routing_summary: RoutingSummary | None = None,
    session_metrics: list[SessionMetricsEntry] | None = None,
    total_cost: float = 0,
    total_latency: float = 0,
    experiment_description: str | None = None,
    task_contexts: dict[str, TaskContext] | None = None,
) -> str:
    import html as html_mod

    description_html = (
        f'<p class="description">{html_mod.escape(experiment_description)}</p>'
        if experiment_description
        else ""
    )

    total_pass = sum(a["pass"] for a in metric_agg.values())
    total_fail = sum(a["fail"] for a in metric_agg.values())
    total_skip = sum(a["skip"] for a in metric_agg.values())
    evaluated = total_pass + total_fail
    overall_rate = total_pass / evaluated * 100 if evaluated else 0

    # Routing section
    routing_html = ""
    if routing_summary:
        total_traces = routing_summary["total_traces"]
        direct = routing_summary["direct_handle"]
        failed = routing_summary["routing_failed"]
        subagent_counts = routing_summary["subagent_counts"]

        routing_bars = ""
        colors = {
            "data_analyst": "#3b82f6",
            "slide_maker": "#8b5cf6",
            "direct": "#6b7280",
            "routing_failed": "#ef4444",
        }
        if total_traces > 0:
            segments = []
            for agent, count in sorted(subagent_counts.items()):
                pct = count / total_traces * 100
                color = colors.get(agent, "#06b6d4")
                segments.append(
                    f'<div style="width:{pct}%;background:{color};height:100%;display:inline-block" title="{agent}: {count}"></div>'
                )
            if direct > 0:
                pct = direct / total_traces * 100
                segments.append(
                    f'<div style="width:{pct}%;background:{colors["direct"]};height:100%;display:inline-block" title="direct: {direct}"></div>'
                )
            if failed > 0:
                pct = failed / total_traces * 100
                segments.append(
                    f'<div style="width:{pct}%;background:{colors["routing_failed"]};height:100%;display:inline-block" title="routing failed: {failed}"></div>'
                )
            routing_bars = f'<div style="width:100%;height:24px;border-radius:6px;overflow:hidden;background:#e5e7eb;margin:8px 0">{"".join(segments)}</div>'

        legend_items = ""
        for agent, count in sorted(subagent_counts.items()):
            color = colors.get(agent, "#06b6d4")
            legend_items += f'<span style="display:inline-flex;align-items:center;margin-right:16px"><span style="width:12px;height:12px;border-radius:3px;background:{color};display:inline-block;margin-right:6px"></span>{agent}: {count}</span>'
        if direct > 0:
            legend_items += f'<span style="display:inline-flex;align-items:center;margin-right:16px"><span style="width:12px;height:12px;border-radius:3px;background:{colors["direct"]};display:inline-block;margin-right:6px"></span>direct: {direct}</span>'
        if failed > 0:
            legend_items += f'<span style="display:inline-flex;align-items:center;margin-right:16px"><span style="width:12px;height:12px;border-radius:3px;background:{colors["routing_failed"]};display:inline-block;margin-right:6px"></span>routing failed: {failed}</span>'

        routing_html = f"""
    <div class="section">
        <h2>Trace Routing</h2>
        <p style="color:#6b7280;margin-bottom:8px">{total_traces} traces evaluated</p>
        {routing_bars}
        <div style="font-size:13px;margin-top:8px">{legend_items}</div>
    </div>"""

    # --- Primary view: Task -> per-metric results -> inline failures ---
    # Group test results by task_id (set on the dict when built from session records)
    tasks_map: dict[str, list[dict]] = {}
    for tr in test_results:
        task_id = tr.get("task_id") or "unknown"
        tasks_map.setdefault(task_id, []).append(tr)

    task_sections_html = ""
    for task_id, task_traces in tasks_map.items():
        # Aggregate metrics for this task only
        task_metric_agg: dict[str, dict] = {}
        for tr in task_traces:
            for m in tr["metrics"]:
                name = m["name"]
                if name not in task_metric_agg:
                    task_metric_agg[name] = {"pass": 0, "fail": 0, "skip": 0}
                if m.get("skipped"):
                    task_metric_agg[name]["skip"] += 1
                elif m["success"]:
                    task_metric_agg[name]["pass"] += 1
                else:
                    task_metric_agg[name]["fail"] += 1

        # Collect failures for this task
        task_failures = [
            f for f in failures if f.get("task_id") == task_id or task_id == "unknown"
        ]

        # Failures indexed by metric name
        failures_by_metric_name: dict[str, list[dict]] = {}
        for f in task_failures:
            failures_by_metric_name.setdefault(f["metric"], []).append(f)

        # Build session index for turn lookup
        sessions_by_id: dict[str, list[dict]] = {}
        for tr in task_traces:
            sid = tr.get("session_id") or tr["trace_id"]
            sessions_by_id.setdefault(sid, []).append(tr)
        for traces in sessions_by_id.values():
            traces.sort(key=lambda t: t.get("turn_index", 0))

        metrics_html = ""
        for metric_name, agg in sorted(task_metric_agg.items()):
            evaluated = agg["pass"] + agg["fail"]
            rate = agg["pass"] / evaluated * 100 if evaluated > 0 else None
            if rate is None:
                m_color = "#9ca3af"
                m_rate_display = "No data"
                m_status_class = "ac-nodata"
                m_status_text = "No data"
            elif agg["fail"] == 0:
                m_color = "#22c55e"
                m_rate_display = f"{rate:.0f}%"
                m_status_class = "ac-pass"
                m_status_text = f"{agg['pass']}/{evaluated} passed"
            elif rate >= 70:
                m_color = "#eab308"
                m_rate_display = f"{rate:.0f}%"
                m_status_class = "ac-fail"
                m_status_text = f"{agg['fail']}/{evaluated} failed"
            else:
                m_color = "#ef4444"
                m_rate_display = f"{rate:.0f}%"
                m_status_class = "ac-fail"
                m_status_text = f"{agg['fail']}/{evaluated} failed"

            # Inline failures for this metric
            metric_failures = failures_by_metric_name.get(metric_name, [])
            failures_html = ""
            for f in metric_failures[:5]:
                reason_text = f["reason"]
                reason_short = html_mod.escape(
                    reason_text[:300] + ("..." if len(reason_text) > 300 else "")
                )
                sid = f.get("session_id") or f["trace_id"]
                turn_idx = f.get("turn_index", 0)
                session_turns = sessions_by_id.get(sid, [])
                relevant_turns = [
                    t for t in session_turns if t.get("turn_index", 0) <= turn_idx
                ]
                turns_expand_html = ""
                for rt in relevant_turns:
                    rt_input = html_mod.escape((rt.get("input") or "")[:1500])
                    rt_output = html_mod.escape((rt.get("output") or "")[:1500])
                    rt_idx = rt.get("turn_index", 0)
                    is_failing = rt_idx == turn_idx
                    turn_border = (
                        "border-left:3px solid #ef4444"
                        if is_failing
                        else "border-left:3px solid #e5e7eb"
                    )
                    turns_expand_html += f"""<div class="ac-turn" style="{turn_border}">
                        <div class="ac-turn-label">Turn {rt_idx + 1}{"  ← failure" if is_failing else ""}</div>
                        <div class="ac-turn-io"><div><div class="context-label">Input</div><pre>{rt_input}</pre></div><div><div class="context-label">Output</div><pre>{rt_output}</pre></div></div>
                    </div>"""
                turn_count = len(relevant_turns)
                failures_html += f"""<div class="ac-failure">
                    <div class="ac-failure-reason">{reason_short}</div>
                    <div class="ac-failure-meta"><code>{f["trace_id"][:12]}</code> · Turn {turn_idx + 1}/{f["total_turns"]} · {f["routed_to"] or "direct"}</div>
                    <details><summary>Show {turn_count} turn{"s" if turn_count != 1 else ""} up to failure</summary><div class="ac-turns">{turns_expand_html}</div></details>
                </div>"""

            failures_block = ""
            if failures_html:
                fail_count = len(metric_failures)
                failures_block = f'<details class="ac-failures-toggle"><summary class="ac-failures-summary">{fail_count} failure{"s" if fail_count != 1 else ""} — click to expand</summary><div class="ac-failures">{failures_html}</div></details>'

            metrics_html += f"""<div class="ac-row">
                <div class="ac-header">
                    <span class="ac-desc">{html_mod.escape(metric_name)}</span>
                    <span class="behaviour-rate" style="color:{m_color};font-size:14px">{m_rate_display}</span>
                    <span class="{m_status_class}">{m_status_text}</span>
                </div>
                {failures_block}
            </div>"""

        task_title = task_id.replace("-", " ").title()
        context_html = ""
        if task_contexts and task_id in task_contexts:
            ctx = task_contexts[task_id]
            ctx_parts = []
            if ctx.get("description"):
                ctx_parts.append(
                    f'<p class="task-description">{html_mod.escape(ctx["description"])}</p>'
                )
            meta_spans = []
            if ctx.get("persona_id"):
                persona_label = ctx["persona_id"].replace("-", " ").title()
                desc_snippet = (ctx.get("persona_description") or "")[:120]
                if desc_snippet:
                    meta_spans.append(
                        f'<span class="task-meta-item"><strong>Persona:</strong> {html_mod.escape(persona_label)} — {html_mod.escape(desc_snippet)}</span>'
                    )
                else:
                    meta_spans.append(
                        f'<span class="task-meta-item"><strong>Persona:</strong> {html_mod.escape(persona_label)}</span>'
                    )
            if ctx.get("fixtures"):
                meta_spans.append(
                    f'<span class="task-meta-item"><strong>Fixtures:</strong> {html_mod.escape(", ".join(ctx["fixtures"]))}</span>'
                )
            outcome_parts = []
            if ctx.get("stop_reason"):
                outcome_parts.append(ctx["stop_reason"].replace("_", " "))
            if ctx.get("total_turns"):
                outcome_parts.append(f'{ctx["total_turns"]} turns')
            if ctx.get("duration_seconds"):
                outcome_parts.append(f'{ctx["duration_seconds"]:.0f}s')
            if outcome_parts:
                meta_spans.append(
                    f'<span class="task-meta-item"><strong>Outcome:</strong> {html_mod.escape(" · ".join(outcome_parts))}</span>'
                )
            if meta_spans:
                ctx_parts.append(f'<div class="task-meta">{"".join(meta_spans)}</div>')
            if ctx_parts:
                context_html = f'<div class="task-context">{"".join(ctx_parts)}</div>'

        task_sections_html += f"""<details class="task-section" open>
            <summary class="task-title">{html_mod.escape(task_title)}</summary>
            <div class="task-body">
                {context_html}
                <div class="ac-list">{metrics_html}</div>
            </div>
        </details>"""

    behaviour_hierarchy_html = (
        f"""
    <div class="section">
        <h2>Tasks</h2>
        <p style="color:#6b7280;font-size:13px;margin-bottom:16px">Results grouped by task. Failed metrics show judge reasoning with expandable traces.</p>
        {task_sections_html}
    </div>"""
        if task_sections_html
        else ""
    )

    # --- Secondary: Metric Summary rows ---
    metric_rows = ""
    for name, agg in sorted(metric_agg.items()):
        rate = agg["pass_rate"] * 100
        metric_evaluated = agg["pass"] + agg["fail"]
        color = (
            "#22c55e"
            if rate == 100 and metric_evaluated > 0
            else "#eab308"
            if rate >= 70
            else "#ef4444"
            if metric_evaluated > 0
            else "#9ca3af"
        )
        rate_str = f"{rate:.1f}%" if metric_evaluated > 0 else "N/A"
        metric_rows += f"""
        <tr>
            <td>{name}</td>
            <td>{agg["pass"]}</td>
            <td>{agg["fail"]}</td>
            <td>{agg["skip"]}</td>
            <td style="color: {color}; font-weight: bold">{rate_str}</td>
        </tr>"""

    import html as html_mod

    failure_cards = ""
    for f in failures[:30]:
        escaped_input = html_mod.escape(f["input"][:3000])
        escaped_output = html_mod.escape(f["output"][:3000])
        escaped_reason = html_mod.escape(f["reason"])
        turn_info = (
            f"Turn {f['turn_index'] + 1}/{f['total_turns']}"
            if f["total_turns"] > 1
            else "Single turn"
        )
        failure_cards += f"""
        <div class="failure-card">
            <div class="failure-header">
                <span class="failure-metric">{f["metric"]}</span>
                <span class="failure-score">Score: {f["score"]:.2f}</span>
                <span class="failure-meta">{turn_info} &middot; {f["routed_to"] or "direct"} &middot; <code>{f["trace_id"][:12]}...</code></span>
            </div>
            <div class="failure-reason">{escaped_reason}</div>
            <details>
                <summary>Show full input/output</summary>
                <div class="failure-context">
                    <div class="context-block">
                        <div class="context-label">Input</div>
                        <pre>{escaped_input}</pre>
                    </div>
                    <div class="context-block">
                        <div class="context-label">Output</div>
                        <pre>{escaped_output}</pre>
                    </div>
                </div>
            </details>
        </div>"""

    # Session-level failure cards
    session_failure_cards = ""
    if session_metrics:
        for sess in session_metrics or []:
            for m in sess.get("metrics", []):
                if not m["success"] and not m.get("skipped"):
                    escaped_reason = html_mod.escape(m["reason"])
                    turns_html = ""
                    for t in sess.get("turns", []):
                        role_class = (
                            "turn-user" if t["role"] == "user" else "turn-assistant"
                        )
                        escaped_content = html_mod.escape(t["content"][:1500])
                        tools_html = ""
                        if t.get("tools"):
                            tools_html = '<div class="turn-tools">'
                            for tool in t["tools"]:
                                tools_html += f'<div class="tool-call"><strong>{html_mod.escape(tool["name"])}</strong>'
                                if tool.get("input"):
                                    tools_html += f'<br><span class="tool-io">in: {html_mod.escape(tool["input"][:200])}</span>'
                                if tool.get("output"):
                                    tools_html += f'<br><span class="tool-io">out: {html_mod.escape(tool["output"][:200])}</span>'
                                tools_html += "</div>"
                            tools_html += "</div>"
                        turns_html += f'<div class="{role_class}"><strong>{t["role"]}</strong><pre>{escaped_content}</pre>{tools_html}</div>'

                    session_failure_cards += f"""
        <div class="failure-card session-failure">
            <div class="failure-header">
                <span class="failure-metric">{m["name"]}</span>
                <span class="failure-score">Score: {m["score"]:.2f}</span>
                <span class="failure-meta">Session &middot; {sess["num_turns"]} turns &middot; <code>{sess["session_id"][:20]}...</code></span>
            </div>
            <div class="failure-reason">{escaped_reason}</div>
            <details>
                <summary>Show full session ({sess["num_turns"]} turns)</summary>
                <div class="session-turns">{turns_html}</div>
            </details>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Orca Eval Report — {run_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px 32px; background: #f9fafb; color: #111827; max-width: 1400px; margin: 0 auto; }}
        h1 {{ font-size: 22px; margin-bottom: 2px; }}
        h2 {{ font-size: 16px; margin: 24px 0 10px; color: #374151; }}
        .subtitle {{ color: #6b7280; margin-bottom: 20px; font-size: 13px; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card-value {{ font-size: 26px; font-weight: 700; }}
        .card-label {{ color: #6b7280; font-size: 12px; margin-top: 2px; }}
        .section {{ margin-bottom: 24px; }}
        code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 11px; }}
        details {{ margin-top: 6px; }}
        details summary {{ cursor: pointer; color: #6b7280; font-size: 13px; }}

        /* Task / Behaviour / AC hierarchy */
        .task-section {{ background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
        .task-title {{ padding: 12px 16px; font-size: 15px; font-weight: 700; color: #111827; cursor: pointer; text-transform: capitalize; background: #f9fafb; border-bottom: 1px solid #e5e7eb; }}
        .task-title:hover {{ background: #f3f4f6; }}
        .task-body {{ padding: 10px 16px 16px; }}
        .task-context {{ margin-bottom: 12px; padding: 10px 12px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; }}
        .task-description {{ font-size: 12px; color: #1e40af; line-height: 1.5; margin-bottom: 6px; }}
        .task-meta {{ display: flex; flex-direction: column; gap: 3px; }}
        .task-meta-item {{ font-size: 11px; color: #374151; line-height: 1.4; }}
        .task-meta-item strong {{ color: #1e3a5f; }}
        .behaviour-block {{ margin-bottom: 14px; }}
        .behaviour-block:last-child {{ margin-bottom: 0; }}
        .behaviour-header {{ display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #f3f4f6; }}
        .behaviour-desc {{ font-size: 13px; font-weight: 600; color: #374151; flex: 1; }}
        .behaviour-rate {{ font-size: 16px; font-weight: 700; }}
        .ac-list {{ padding-left: 12px; margin-top: 6px; }}
        .ac-row {{ margin-bottom: 6px; padding: 8px 10px; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb; }}
        .ac-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
        .ac-desc {{ font-size: 12px; color: #374151; flex: 1; }}
        .ac-metrics-ids {{ font-size: 10px; color: #9ca3af; font-family: monospace; }}
        .ac-pass {{ font-size: 11px; font-weight: 600; color: #166534; background: #dcfce7; padding: 2px 6px; border-radius: 4px; white-space: nowrap; }}
        .ac-fail {{ font-size: 11px; font-weight: 600; color: #991b1b; background: #fecaca; padding: 2px 6px; border-radius: 4px; white-space: nowrap; }}
        .ac-nodata {{ font-size: 11px; color: #9ca3af; }}
        .ac-failures-toggle {{ margin-top: 6px; }}
        .ac-failures-summary {{ font-size: 11px; color: #991b1b; cursor: pointer; padding: 2px 0; }}
        .ac-failures {{ margin-top: 6px; padding-left: 8px; border-left: 3px solid #fecaca; }}
        .ac-failure {{ margin-bottom: 8px; padding: 6px 10px; background: #fef2f2; border-radius: 5px; }}
        .ac-failure.session-type {{ background: #fffbeb; border-left: 3px solid #f59e0b; }}
        .ac-failure-reason {{ font-size: 11px; color: #1f2937; line-height: 1.4; margin-bottom: 3px; }}
        .ac-failure-meta {{ font-size: 10px; color: #6b7280; margin-bottom: 3px; }}
        .ac-turns {{ margin-top: 6px; }}
        .ac-turn {{ padding: 6px 8px; margin-bottom: 4px; border-radius: 5px; background: white; }}
        .ac-turn-label {{ font-size: 10px; font-weight: 600; color: #6b7280; margin-bottom: 3px; }}
        .ac-turn-io {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
        .ac-turn-io pre {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px; padding: 6px; font-size: 10px; white-space: pre-wrap; word-break: break-word; max-height: 250px; overflow-y: auto; }}
        .context-label {{ font-size: 9px; font-weight: 600; color: #6b7280; text-transform: uppercase; margin-bottom: 2px; }}

        /* Session turns (for session-level failures) */
        .turn-user, .turn-assistant {{ padding: 5px 8px; margin-bottom: 3px; border-radius: 5px; }}
        .turn-user {{ background: #eff6ff; border-left: 3px solid #3b82f6; }}
        .turn-assistant {{ background: #f0fdf4; border-left: 3px solid #22c55e; }}
        .turn-user pre, .turn-assistant pre {{ font-size: 10px; white-space: pre-wrap; word-break: break-word; max-height: 180px; overflow-y: auto; margin: 3px 0 0; }}

        /* Secondary sections */
        .secondary-section {{ margin-top: 36px; border-top: 2px solid #e5e7eb; padding-top: 16px; }}
        .secondary-section > details > summary {{ font-size: 15px; font-weight: 600; color: #6b7280; padding: 6px 0; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; margin-top: 12px; }}
        th {{ background: #f3f4f6; text-align: left; padding: 10px 12px; font-size: 13px; color: #374151; }}
        td {{ padding: 10px 12px; border-top: 1px solid #e5e7eb; font-size: 13px; }}
        tr:hover {{ background: #f9fafb; }}

        /* Trace detail (secondary) */
        .trace-card {{ background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .trace-card summary {{ padding: 14px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; font-size: 13px; }}
        .trace-card summary:hover {{ background: #f9fafb; border-radius: 8px; }}
        .trace-meta {{ color: #6b7280; font-size: 12px; margin-left: auto; }}
        .trace-body {{ padding: 0 16px 16px; }}
        .session-turn {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; margin-bottom: 10px; }}
        .session-turn-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 13px; }}
        .session-turn-io {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 8px; }}
        .io-block pre {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; font-size: 11px; white-space: pre-wrap; word-break: break-word; max-height: 500px; overflow-y: auto; }}
        .metrics-dropdown {{ margin-top: 6px; }}
        .metrics-dropdown summary {{ cursor: pointer; color: #6b7280; font-size: 12px; font-weight: 500; padding: 4px 0; }}
        .trace-metrics-list {{ display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }}
        .trace-metric {{ padding: 8px 12px; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb; }}
        .trace-metric-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }}
        .trace-metric-name {{ font-size: 12px; font-weight: 500; color: #374151; }}
        .trace-metric-reason {{ font-size: 12px; color: #6b7280; line-height: 1.4; }}
        .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .badge-pass {{ background: #dcfce7; color: #166534; }}
        .badge-fail {{ background: #fecaca; color: #991b1b; }}
        .badge-skip {{ background: #e5e7eb; color: #6b7280; }}
    </style>
</head>
<body>
    <h1>Orca Eval Report</h1>
    {description_html}
    <p class="subtitle">Run: {run_id} &middot; {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

    <div class="summary-cards">
        <div class="card">
            <div class="card-value">{len(test_results)}</div>
            <div class="card-label">Traces Evaluated</div>
        </div>
        <div class="card">
            <div class="card-value">{len(metric_agg)}</div>
            <div class="card-label">Metrics</div>
        </div>
        <div class="card">
            <div class="card-value" style="color: {"#22c55e" if overall_rate >= 80 else "#eab308" if overall_rate >= 50 else "#ef4444"}">{overall_rate:.1f}%</div>
            <div class="card-label">Pass Rate (excl. skipped)</div>
        </div>
        <div class="card">
            <div class="card-value" style="color: #ef4444">{total_fail}</div>
            <div class="card-label">Failures</div>
        </div>
        <div class="card">
            <div class="card-value" style="color: #9ca3af">{total_skip}</div>
            <div class="card-label">Skipped</div>
        </div>
        <div class="card">
            <div class="card-value">{total_latency:.1f}s</div>
            <div class="card-label">Latency</div>
        </div>
        <div class="card">
            <div class="card-value">{"$" + f"{total_cost:.4f}" if total_cost else "N/A"}</div>
            <div class="card-label">Judge Cost</div>
        </div>
    </div>
    {routing_html}
    {behaviour_hierarchy_html}

    <div class="secondary-section">
        <details>
            <summary>Metric Summary (flat table)</summary>
            <table>
                <thead><tr><th>Metric</th><th>Pass</th><th>Fail</th><th>Skip</th><th>Rate</th></tr></thead>
                <tbody>{metric_rows}</tbody>
            </table>
        </details>
    </div>

    <div class="secondary-section">
        <details>
            <summary>Per-Trace Detail (all metrics per session)</summary>
            <p style="color:#6b7280;margin:12px 0;font-size:13px">All metrics for each trace, with score and judge reasoning.</p>
            {_render_trace_details(test_results, html_mod)}
        </details>
    </div>
</body>
</html>"""
