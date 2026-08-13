"""Individual HTML section renderers for the eval report.

Each function returns an HTML fragment string. They are pure (no side effects)
and take only the data they need.
"""

from __future__ import annotations

import html as html_mod
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metis.engine.extractor.types import RoutingSummary

    from .generator import TaskContext


def render_summary_cards(
    num_traces: int,
    num_metrics: int,
    overall_rate: float,
    total_fail: int,
    total_skip: int,
    total_latency: float,
    total_cost: float,
) -> str:
    rate_color = (
        "#22c55e"
        if overall_rate >= 80
        else "#eab308"
        if overall_rate >= 50
        else "#ef4444"
    )
    cost_display = f"${total_cost:.4f}" if total_cost else "N/A"
    return f"""<div class="summary-cards">
        <div class="card">
            <div class="card-value">{num_traces}</div>
            <div class="card-label">Traces Evaluated</div>
        </div>
        <div class="card">
            <div class="card-value">{num_metrics}</div>
            <div class="card-label">Metrics</div>
        </div>
        <div class="card">
            <div class="card-value" style="color: {rate_color}">{overall_rate:.1f}%</div>
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
            <div class="card-value">{cost_display}</div>
            <div class="card-label">Judge Cost</div>
        </div>
    </div>"""


def render_routing_section(routing_summary: RoutingSummary | None) -> str:
    if not routing_summary:
        return ""

    total_traces = routing_summary["total_traces"]
    direct = routing_summary["direct_handle"]
    failed = routing_summary["routing_failed"]
    subagent_counts = routing_summary["subagent_counts"]

    colors = {
        "data_analyst": "#3b82f6",
        "slide_maker": "#8b5cf6",
        "direct": "#6b7280",
        "routing_failed": "#ef4444",
    }

    routing_bars = ""
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

    return f"""
    <div class="section">
        <h2>Trace Routing</h2>
        <p style="color:#6b7280;margin-bottom:8px">{total_traces} traces evaluated</p>
        {routing_bars}
        <div style="font-size:13px;margin-top:8px">{legend_items}</div>
    </div>"""


def render_task_sections(
    test_results: list[dict],
    task_contexts: dict[str, TaskContext] | None = None,
) -> str:
    tasks_map: dict[str, list[dict]] = {}
    for tr in test_results:
        task_id = tr.get("task_id") or "unknown"
        tasks_map.setdefault(task_id, []).append(tr)

    failures = _extract_failures(test_results)

    if not tasks_map:
        return ""

    task_sections_html = ""
    for task_id, task_traces in tasks_map.items():
        task_sections_html += _render_single_task(
            task_id, task_traces, failures, task_contexts
        )

    return f"""
    <div class="section">
        <h2>Tasks</h2>
        <p style="color:#6b7280;font-size:13px;margin-bottom:16px">Results grouped by task. Failed metrics show judge reasoning with expandable traces.</p>
        {task_sections_html}
    </div>"""


def _render_single_task(
    task_id: str,
    task_traces: list[dict],
    failures: list[dict],
    task_contexts: dict[str, TaskContext] | None,
) -> str:
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

    task_failures = [
        f for f in failures if f.get("task_id") == task_id or task_id == "unknown"
    ]
    failures_by_metric_name: dict[str, list[dict]] = {}
    for f in task_failures:
        failures_by_metric_name.setdefault(f["metric"], []).append(f)

    sessions_by_id: dict[str, list[dict]] = {}
    for tr in task_traces:
        sid = tr.get("session_id") or tr["trace_id"]
        sessions_by_id.setdefault(sid, []).append(tr)
    for traces in sessions_by_id.values():
        traces.sort(key=lambda t: t.get("turn_index", 0))

    metrics_html = ""
    for metric_name, agg in sorted(task_metric_agg.items()):
        metrics_html += _render_task_metric_row(
            metric_name, agg, failures_by_metric_name, sessions_by_id
        )

    task_title = task_id.replace("-", " ").title()
    context_html = _render_task_context(task_id, task_contexts)

    return f"""<details class="task-section" open>
            <summary class="task-title">{html_mod.escape(task_title)}</summary>
            <div class="task-body">
                {context_html}
                <div class="ac-list">{metrics_html}</div>
            </div>
        </details>"""


def _render_task_metric_row(
    metric_name: str,
    agg: dict,
    failures_by_metric_name: dict[str, list[dict]],
    sessions_by_id: dict[str, list[dict]],
) -> str:
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

    metric_failures = failures_by_metric_name.get(metric_name, [])
    failures_block = _render_inline_failures(metric_failures, sessions_by_id)

    return f"""<div class="ac-row">
                <div class="ac-header">
                    <span class="ac-desc">{html_mod.escape(metric_name)}</span>
                    <span class="behaviour-rate" style="color:{m_color};font-size:14px">{m_rate_display}</span>
                    <span class="{m_status_class}">{m_status_text}</span>
                </div>
                {failures_block}
            </div>"""


def _render_inline_failures(
    metric_failures: list[dict],
    sessions_by_id: dict[str, list[dict]],
) -> str:
    if not metric_failures:
        return ""

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
                    <div class="ac-failure-meta"><code>{f["trace_id"][:12]}</code> \xb7 Turn {turn_idx + 1}/{f["total_turns"]} \xb7 {f["routed_to"] or "direct"}</div>
                    <details><summary>Show {turn_count} turn{"s" if turn_count != 1 else ""} up to failure</summary><div class="ac-turns">{turns_expand_html}</div></details>
                </div>"""

    fail_count = len(metric_failures)
    return f'<details class="ac-failures-toggle"><summary class="ac-failures-summary">{fail_count} failure{"s" if fail_count != 1 else ""} — click to expand</summary><div class="ac-failures">{failures_html}</div></details>'


def _render_task_context(
    task_id: str,
    task_contexts: dict[str, TaskContext] | None,
) -> str:
    if not task_contexts or task_id not in task_contexts:
        return ""

    ctx = task_contexts[task_id]
    ctx_parts: list[str] = []

    description = ctx.get("description")
    if description:
        ctx_parts.append(
            f'<p class="task-description">{html_mod.escape(description)}</p>'
        )

    meta_spans: list[str] = []

    personas = ctx.get("personas", [])
    if personas:
        persona_items: list[str] = []
        for p in personas:
            label = p["id"].replace("-", " ").title()
            snippet = (p.get("description") or "")[:120]
            outcome_bits: list[str] = []
            if p.get("stop_reason"):
                outcome_bits.append(p["stop_reason"].replace("_", " "))
            if p.get("total_turns"):
                outcome_bits.append(f"{p['total_turns']} turns")
            if p.get("duration_seconds"):
                outcome_bits.append(f"{p['duration_seconds']:.0f}s")
            suffix = f" ({' · '.join(outcome_bits)})" if outcome_bits else ""
            if snippet:
                persona_items.append(
                    f"{html_mod.escape(label)} — {html_mod.escape(snippet)}{html_mod.escape(suffix)}"
                )
            else:
                persona_items.append(
                    f"{html_mod.escape(label)}{html_mod.escape(suffix)}"
                )
        if len(persona_items) == 1:
            meta_spans.append(
                f'<span class="task-meta-item"><strong>Persona:</strong> {persona_items[0]}</span>'
            )
        else:
            items_html = "".join(f"<li>{item}</li>" for item in persona_items)
            meta_spans.append(
                f'<span class="task-meta-item"><strong>Personas:</strong><ul style="margin:2px 0 0 16px;padding:0">{items_html}</ul></span>'
            )
    elif ctx.get("persona_id"):
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

    fixtures = ctx.get("fixtures")
    if fixtures:
        meta_spans.append(
            f'<span class="task-meta-item"><strong>Fixtures:</strong> {html_mod.escape(", ".join(fixtures))}</span>'
        )

    if not personas:
        outcome_parts: list[str] = []
        stop_reason = ctx.get("stop_reason")
        if stop_reason:
            outcome_parts.append(stop_reason.replace("_", " "))
        total_turns = ctx.get("total_turns")
        if total_turns:
            outcome_parts.append(f"{total_turns} turns")
        duration = ctx.get("duration_seconds")
        if duration:
            outcome_parts.append(f"{duration:.0f}s")
        if outcome_parts:
            outcome_text = html_mod.escape(" · ".join(outcome_parts))
            meta_spans.append(
                f'<span class="task-meta-item"><strong>Outcome:</strong> {outcome_text}</span>'
            )

    if meta_spans:
        ctx_parts.append(f'<div class="task-meta">{"".join(meta_spans)}</div>')

    if not ctx_parts:
        return ""
    return f'<div class="task-context">{"".join(ctx_parts)}</div>'


def render_metric_table(metric_agg: dict) -> str:
    metric_rows = ""
    for name, agg in sorted(metric_agg.items()):
        rate = agg["pass_rate"] * 100
        metric_evaluated = agg["pass_count"] + agg["fail"]
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
            <td>{agg["pass_count"]}</td>
            <td>{agg["fail"]}</td>
            <td>{agg["skip"]}</td>
            <td style="color: {color}; font-weight: bold">{rate_str}</td>
        </tr>"""

    return f"""<div class="secondary-section">
        <details>
            <summary>Metric Summary (flat table)</summary>
            <table>
                <thead><tr><th>Metric</th><th>Pass</th><th>Fail</th><th>Skip</th><th>Rate</th></tr></thead>
                <tbody>{metric_rows}</tbody>
            </table>
        </details>
    </div>"""


def render_trace_details(test_results: list[dict]) -> str:
    sessions: OrderedDict[str, list[dict]] = OrderedDict()
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
            turns_html += _render_trace_turn(turn_idx, result)

        html_out += f"""
        <details class="trace-card" {"open" if session_fail > 0 else ""}>
            <summary>
                <span style="color:{session_color};font-weight:600">Session {session_idx}</span>
                <code>{sid[:24]}</code>
                <span class="trace-meta">{total_turns} turn(s) &middot; {session_pass}P {session_fail}F {session_skip}S</span>
            </summary>
            <div class="trace-body">{turns_html}</div>
        </details>"""

    return f"""<div class="secondary-section">
        <details>
            <summary>Per-Trace Detail (all metrics per session)</summary>
            <p style="color:#6b7280;margin:12px 0;font-size:13px">All metrics for each trace, with score and judge reasoning.</p>
            {html_out}
        </details>
    </div>"""


def _render_trace_turn(turn_idx: int, result: dict) -> str:
    trace_id = result["trace_id"][:12]
    routed_to = result.get("routed_to", "direct")
    escaped_input = html_mod.escape(result["input"] or "")
    escaped_output = html_mod.escape(result["output"] or "")

    n_pass = sum(1 for m in result["metrics"] if m["success"] and not m.get("skipped"))
    n_fail = sum(
        1 for m in result["metrics"] if not m["success"] and not m.get("skipped")
    )
    n_skip = sum(1 for m in result["metrics"] if m.get("skipped"))
    turn_color = "#22c55e" if n_fail == 0 else "#ef4444"

    metric_rows = ""
    for m in sorted(
        result["metrics"],
        key=lambda x: (x.get("skipped", False), x["success"], x["score"]),
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

    return f"""
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
