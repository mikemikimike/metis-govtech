"""Top panel: progress bars, scenario/run status table."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .state import SimulationState


def _format_elapsed(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}m{s:02d}s"


def render_dashboard(state: SimulationState) -> RenderableType:
    """Build the dashboard renderable from current state."""
    parts: list[RenderableType] = []

    # Header
    header = Text()
    header.append("METIS Engine Simulate", style="bold")
    header.append(f" — {state.experiment_id}\n")
    header.append(f"Elapsed: {_format_elapsed(state.elapsed_seconds)}\n")
    parts.append(header)

    # Progress bars
    total_scenarios = len(state.scenarios)
    total_runs = state.total_runs

    scenarios_table = Table.grid(padding=(0, 1))
    scenarios_table.add_row(
        Text("Scenarios:", style="dim"),
        ProgressBar(
            total=total_scenarios, completed=state.completed_scenarios, width=20
        ),
        Text(f"{state.completed_scenarios}/{total_scenarios}"),
    )
    scenarios_table.add_row(
        Text("Runs:", style="dim"),
        ProgressBar(total=total_runs, completed=state.completed_runs, width=20),
        Text(f"{state.completed_runs}/{total_runs}"),
    )
    parts.append(scenarios_table)
    parts.append(Text(""))

    # Active scenarios (may be multiple with concurrent workers)
    active_scenarios = [sc for sc in state.scenarios if sc.phase == "active"]
    for active in active_scenarios:
        active_text = Text()
        active_text.append(f"Ongoing scenario: {active.scenario_id}\n", style="bold")
        for run in active.runs:
            worker_tag = f"[w{run.worker_id}] " if run.worker_id is not None else ""
            if run.phase == "simulating":
                turn_info = ""
                if run.current_turn is not None:
                    turn_info = f"[turn {run.current_turn}/{run.max_turns}]"
                detail = run.turn_detail or ""
                active_text.append(
                    f"  ● {worker_tag}{run.persona_id} simulating "
                    f"{turn_info} {detail}\n",
                    style="yellow",
                )
            elif run.phase == "completed":
                dur = _format_duration(run.duration_seconds or 0)
                active_text.append(
                    f"  ✓ {worker_tag}{run.persona_id} "
                    f"[completed trial {run.trial}/{run.num_trials}]  {dur}\n",
                    style="green",
                )
            elif run.phase == "failed":
                active_text.append(
                    f"  ✗ {worker_tag}{run.persona_id} [failed: {run.stop_reason}]\n",
                    style="red",
                )
            elif run.phase == "pending":
                active_text.append(
                    f"  ○ {run.persona_id} [pending]\n",
                    style="dim",
                )
        parts.append(active_text)

    # Completed scenarios
    completed = [sc for sc in state.scenarios if sc.phase == "completed"]
    if completed:
        comp_text = Text()
        comp_text.append("Completed scenarios:\n", style="dim")
        for sc in completed:
            run_count = len(sc.runs)
            total_dur = sum(r.duration_seconds or 0 for r in sc.runs)
            comp_text.append(
                f"  ✓ {sc.scenario_id} ({run_count} run{'s' if run_count > 1 else ''})  "
                f"{_format_duration(total_dur)}\n",
                style="green",
            )
        parts.append(comp_text)

    # Pending count
    pending = state.pending_scenario_count
    if pending > 0:
        parts.append(
            Text(
                f"Pending: {pending} scenario{'s' if pending > 1 else ''}", style="dim"
            )
        )

    return Group(*parts)
