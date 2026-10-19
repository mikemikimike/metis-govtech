"""Terminal summary and persistence of the target evaluation report.

Produces:
1. A terminal summary table.
2. The target evaluation report, as an HTML page and as JSON data.

The report joins each grader result to its Criterion in the Specification. A reader
can see which Behaviour needs attention and which Persona or Scenario is hard to test.
Every number comes from a file the run already wrote; no model writes any of its text.
A run with no target specification writes no report.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from metis.core import execution_layout
from metis.core.logging import get_logger
from metis.insights._aggregation import aggregate_graders
from metis.insights._models import Report
from metis.insights._report import build_report, load_report_sources
from metis.insights._report_page import render_report_page

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from metis.insights._legacy_results import (
        EvaluationResults,
        SessionReport,
        TurnReport,
    )

logger = get_logger(__name__)


def format_terminal_summary(
    turn_results: list[TurnReport],
    run_id: str,
    routing_summary: Mapping[str, Any] | None = None,
    session_results: list[SessionReport] | None = None,
) -> str:
    """Print a compact terminal summary of all grader results."""
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

    grader_agg = aggregate_graders(
        [t.model_dump() for t in turn_results],
        [s.model_dump() for s in session_results] if session_results else None,
    )

    lines.append(f"  {'Grader':<40} {'Pass':>6} {'Fail':>6} {'Skip':>6} {'Rate':>7}")
    lines.append(f"  {'-' * 40} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 7}")

    for name, agg in sorted(grader_agg.items()):
        evaluated = agg["pass_count"] + agg["fail"]
        rate = agg["pass_count"] / evaluated if evaluated > 0 else 0
        marker = " " if agg["fail"] == 0 else "!"
        rate_str = f"{rate * 100:.1f}%" if evaluated > 0 else "  N/A"
        lines.append(
            f" {marker}{name:<40} {agg['pass_count']:>6} {agg['fail']:>6} {agg['skip']:>6} {rate_str:>7}"
        )

    total_pass = sum(a["pass_count"] for a in grader_agg.values())
    total_fail = sum(a["fail"] for a in grader_agg.values())
    total_skip = sum(a["skip"] for a in grader_agg.values())
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
    results: EvaluationResults, experiment_dir: Path
) -> tuple[Path, Path] | None:
    """Write the target evaluation report into `experiment_dir/outputs/reports/`.

    The report reads `inputs/specification.yaml` and `outputs/trials/*/record.json` from the
    experiment directory. `simulate` freezes the input document there. A run with no
    specification gets no report, and that is not an error.

    :returns: The HTML path and the JSON path, or `None` when there is no specification.
    """
    sources = load_report_sources(experiment_dir)
    if sources is None:
        return None
    specification, persona_of, trial_outcomes = sources

    report = build_report(
        specification,
        [t.model_dump() for t in results.turn_results],
        persona_of=persona_of,
        session_graders=[s.model_dump() for s in results.session_results]
        if results.session_results
        else None,
        run_id=results.run_id,
        timestamp=datetime.now().isoformat(),
        latency_seconds=results.latency_seconds,
        timings=results.timings,
        routing=results.routing,
        trial_outcomes=trial_outcomes,
    )

    report_model = Report.model_validate(report)

    reports_dir = experiment_dir / execution_layout.REPORTS
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "report.json"
    html_path = reports_dir / "report.html"
    # encoding is explicit because write_text() otherwise uses the locale encoding,
    # which is cp1252 on Windows. The rendered page contains characters outside it
    # (U+2192 among them), so the write would open the file, truncate it, then raise
    # UnicodeEncodeError, leaving a 0-byte report.html behind.
    json_path.write_text(
        json.dumps(report_model.model_dump(by_alias=True), indent=1, default=str)
        + "\n",
        encoding="utf-8",
    )
    html_path.write_text(
        render_report_page(report, title=report["target"]), encoding="utf-8"
    )

    logger.info(
        "report_written",
        features=len(report["features"]),
        behaviours=len(report["behaviours"]),
        criteria=len(report["criteria"]),
        scored=sum(1 for c in report["criteria"].values() if c["rate"] is not None),
        unresolved=len(report["unresolved"]),
    )
    return html_path, json_path
