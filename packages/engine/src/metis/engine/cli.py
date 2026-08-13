"""Command-line interface for metis-engine."""

import logging
import os
import shutil
import signal
import sys
import threading
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import typer
from dotenv import load_dotenv

from metis.core.console import console
from metis.engine import __version__
from metis.engine.logging import (
    OrchestrationLogger,
    setup_engine_logging,
    teardown_engine_logging,
)
from metis.engine.tui import (
    RunState,
    ScenarioState,
    SimulationState,
    TailBuffer,
    TUIContext,
)

app = typer.Typer(help="Run METIS evaluations against traces.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"metis-engine {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True
    ),
) -> None:
    pass


def _find_project_root() -> Path:
    """Walk up from CWD to find pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current


def _validate_inputs(input_dir: Path) -> None:
    """Validate all experiment inputs upfront before simulation.

    Fails fast on the first error with a clear message and sys.exit(1).
    """
    import importlib

    from deepeval.metrics import BaseMetric
    from deepeval.metrics.base_metric import BaseConversationalMetric
    from pydantic import ValidationError

    from metis.engine.simulation.types import Experiment

    if not input_dir.is_dir():
        console.print(
            f"Error: input directory '{input_dir}' does not exist", style="bold red"
        )
        sys.exit(1)

    experiment_path = input_dir / "experiment.yaml"
    if not experiment_path.exists():
        console.print(
            f"Error: missing required file 'experiment.yaml' in {input_dir}",
            style="bold red",
        )
        sys.exit(1)

    try:
        experiment = Experiment.load_file(experiment_path)
    except ValidationError as e:
        first = e.errors()[0]
        loc = " → ".join(str(part) for part in first["loc"]) if first["loc"] else "root"
        console.print(
            f"Error: experiment.yaml validation failed: {loc} — {first['msg']}",
            style="bold red",
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"Error: failed to parse experiment.yaml: {e}", style="bold red")
        sys.exit(1)

    seen_personas: set[str] = set()
    for persona in experiment.personas:
        if persona.id in seen_personas:
            console.print(
                f"Error: duplicate persona id '{persona.id}' in experiment.yaml",
                style="bold red",
            )
            sys.exit(1)
        seen_personas.add(persona.id)

    seen_scenarios: set[str] = set()
    for scenario in experiment.scenarios:
        if scenario.id in seen_scenarios:
            console.print(
                f"Error: duplicate scenario id '{scenario.id}' in experiment.yaml",
                style="bold red",
            )
            sys.exit(1)
        seen_scenarios.add(scenario.id)

    defined_personas = {p.id for p in experiment.personas}
    for scenario in experiment.scenarios:
        for ref in scenario.persona_refs:
            if ref not in defined_personas:
                available = ", ".join(sorted(defined_personas))
                console.print(
                    f"Error: scenario '{scenario.id}' references unknown persona '{ref}' (available: {available})",
                    style="bold red",
                )
                sys.exit(1)

    fixtures_dir = input_dir / "fixtures"
    for scenario in experiment.scenarios:
        for fixture in scenario.fixtures:
            if not (fixtures_dir / fixture).exists():
                console.print(
                    f"Error: scenario '{scenario.id}' references fixture '{fixture}' which does not exist in {fixtures_dir}",
                    style="bold red",
                )
                sys.exit(1)

    for scenario in experiment.scenarios:
        for metric_ref in scenario.metric_refs:
            fqn = metric_ref.fqn
            parts = fqn.rsplit(".", 1)
            if len(parts) != 2:
                console.print(
                    f"Error: metric '{fqn}' is not a valid fully-qualified name",
                    style="bold red",
                )
                sys.exit(1)
            module_path, class_name = parts
            try:
                module = importlib.import_module(module_path)
            except Exception as e:
                console.print(
                    f"Error: metric '{fqn}' could not be imported: {type(e).__name__}: {e}",
                    style="bold red",
                )
                sys.exit(1)
            cls = getattr(module, class_name, None)
            if cls is None:
                console.print(
                    f"Error: metric '{fqn}' could not be imported: "
                    f"module '{module_path}' has no attribute '{class_name}'",
                    style="bold red",
                )
                sys.exit(1)
            if not (
                isinstance(cls, type)
                and (
                    issubclass(cls, BaseMetric)
                    or issubclass(cls, BaseConversationalMetric)
                )
            ):
                console.print(
                    f"Error: metric '{fqn}' is not a subclass of "
                    f"deepeval.metrics.BaseMetric or "
                    f"BaseConversationalMetric",
                    style="bold red",
                )
                sys.exit(1)


def _format_final_summary(state: "Any", experiment_dir: str, log_dir: str) -> str:
    """Build the static final summary printed after TUI exits."""
    total = state.total_runs
    completed = state.completed_runs
    passed = sum(
        1 for sc in state.scenarios for r in sc.runs if r.stop_reason == "goal_achieved"
    )
    failed = completed - passed

    elapsed = state.elapsed_seconds
    h = int(elapsed) // 3600
    m = (int(elapsed) % 3600) // 60

    elapsed_str = f"{h}h {m:02d}m" if h > 0 else f"{m}m"

    lines = [
        f"METIS {state.experiment_id} — completed in {elapsed_str}",
        f"Simulation: {completed}/{total} runs ({passed} passed, {failed} failed)",
        f"Logs:   {log_dir}/",
    ]
    return "\n".join(lines)


@app.command()
def simulate(
    input_dir: Path = typer.Option(
        ..., "--input-dir", help="Directory containing experiment.yaml and fixtures/"
    ),
    langfuse_timeout: int = typer.Option(
        90, "--langfuse-timeout", help="Seconds to wait for Langfuse traces"
    ),
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True, help="Increase logging verbosity"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", help="Suppress output below ERROR level"
    ),
    no_tui: bool = typer.Option(
        False, "--no-tui", help="Disable TUI even in a terminal"
    ),
    log_format: Literal["text", "json"] = typer.Option(
        "text", "--log-format", help="Log file format: text or json"
    ),
    log_dir: Path | None = typer.Option(
        None,
        "--log-dir",
        help="Override log directory (default: co-located with results)",
    ),
    concurrency: int = typer.Option(
        5, "--concurrency", "-c", help="Max parallel simulation workers"
    ),
) -> None:
    """Run end-to-end simulation, evaluation, and report."""
    load_dotenv()

    use_tui = not no_tui and sys.stderr.isatty()

    if quiet:
        log_level = "ERROR"
    elif verbose >= 2:
        log_level = "DEBUG"
    elif verbose >= 1:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    # Configure logging BEFORE importing harness modules — they create
    # module-level loggers that cache the processor chain.
    # When TUI is active, set DEBUG so all events flow through the router.
    from metis.core.logging import configure_logging

    configure_logging(level="DEBUG" if use_tui else log_level)

    # Disable structlog's per-proxy bind caching so that module-level loggers
    # (created at import time below) always use the latest processor chain —
    # required for setup_engine_logging to inject the router after import.
    import structlog

    structlog.configure(cache_logger_on_first_use=False)

    # Deferred imports: these pull in playwright, deepeval, langfuse, and openai
    # which are expensive to load. Keeping them here avoids penalising --help/--version.
    from metis.engine.evaluation import evaluate
    from metis.engine.extractor import fetch_by_session_id, get_langfuse_client
    from metis.engine.reporting import TaskContext, generate_report
    from metis.engine.simulation.experiment import HarnessConfig, run_experiment
    from metis.engine.simulation.types import Experiment, RunRecord

    if not os.environ.get("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"):
        os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "300"

    project_root = _find_project_root()

    resolved_input_dir = input_dir.resolve()
    _validate_inputs(resolved_input_dir)

    experiment_path = resolved_input_dir / "experiment.yaml"
    fixtures_dir = resolved_input_dir / "fixtures"
    experiment = Experiment.load_file(experiment_path)

    suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
    experiment_dir = project_root / "experiments" / f"{experiment.id}-{suffix}"
    experiment_dir.mkdir(parents=True)

    shutil.copytree(resolved_input_dir, experiment_dir / "inputs")

    personas_by_id = {p.id: p for p in experiment.personas}

    config = HarnessConfig.load()
    headed = os.environ.get("HEADED", "").lower() == "true"

    console.print(f"\n{'=' * 60}")
    console.print("  SIMULATION")
    console.print(f"{'=' * 60}")
    console.print(f"  Experiment: {experiment_dir}")
    console.print(f"  Input: {resolved_input_dir}")
    console.print(f"  Mode: {'headed' if headed else 'headless'}\n")

    # --- Set up logging and TUI ---
    resolved_log_dir = log_dir or (experiment_dir / "logs")
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    # Build initial SimulationState from the experiment config
    scenarios_state: list[ScenarioState] = []
    total_run_count = 0
    for scenario in experiment.scenarios:
        run_states: list[RunState] = []
        for persona_ref in scenario.persona_refs:
            for trial_idx in range(scenario.num_trials):
                total_run_count += 1
                run_states.append(
                    RunState(
                        scenario_id=scenario.id,
                        persona_id=persona_ref,
                        trial=trial_idx + 1,
                        num_trials=scenario.num_trials,
                        phase="pending",
                        current_turn=None,
                        max_turns=20,  # RunConfig default; overwritten by update_run_turn() during simulation
                        turn_detail="",
                        duration_seconds=None,
                        stop_reason=None,
                    )
                )
        scenarios_state.append(
            ScenarioState(
                scenario_id=scenario.id,
                runs=run_states,
                phase="pending",
            )
        )

    sim_state = SimulationState(
        experiment_id=experiment.id,
        scenarios=scenarios_state,
        total_runs=total_run_count,
    )

    display_level = getattr(logging, log_level)

    tail_buffers = {
        f"w{i}": TailBuffer(max_lines=15, min_level=display_level)
        for i in range(concurrency)
    }
    log_router = setup_engine_logging(
        log_dir=resolved_log_dir,
        log_format=log_format,
        tail_buffers=tail_buffers,
        use_tui=use_tui,
    )
    orchestration_logger = OrchestrationLogger(
        log_dir=resolved_log_dir, log_format=log_format
    )

    tui_ctx: TUIContext | None = None
    if use_tui:
        tui_ctx = TUIContext(state=sim_state, tail_buffers=tail_buffers)

    _interrupt_count = 0
    _interrupt_lock = threading.Lock()

    def _handle_sigint(signum: int, frame: Any) -> None:
        nonlocal _interrupt_count
        with _interrupt_lock:
            _interrupt_count += 1
            if _interrupt_count >= 2:
                console.print("\nForce abort.", style="bold red")
                sys.exit(130)
            console.print(
                "\nInterrupt received — finishing current turn. Press Ctrl+C again to abort.",
                style="yellow",
            )

    prev_handler = signal.signal(signal.SIGINT, _handle_sigint)
    try:
        with tui_ctx if tui_ctx else nullcontext():
            run_experiment(
                config=config,
                experiment=experiment,
                personas_by_id=personas_by_id,
                output_dir=experiment_dir,
                fixtures_dir=fixtures_dir,
                headed=headed,
                concurrency=concurrency,
                state=sim_state,
                orchestration_logger=orchestration_logger,
                log_router=log_router,
                tui_ctx=tui_ctx,
            )
    finally:
        signal.signal(signal.SIGINT, prev_handler)
        teardown_engine_logging(log_router)
        orchestration_logger.close()

    summary = _format_final_summary(
        sim_state,
        str(experiment_dir),
        str(resolved_log_dir),
    )
    console.print(summary)

    files = sorted(
        experiment_dir.glob("runs/*/record.json"), key=lambda p: p.stat().st_mtime
    )
    records: list[RunRecord] = [RunRecord.load_file(f) for f in files]

    if not records:
        console.print("No run records found.")
        sys.exit(1)

    console.print(f"  Loaded {len(records)} run record(s)")

    langfuse = get_langfuse_client()
    eval_results = []
    failed = 0

    for i, record in enumerate(records):
        session_id = record.target_session_id
        persona = record.config.persona
        task = record.config.scenario
        metric_refs = record.config.metric_refs

        console.print(f"\n\n{'#' * 60}")
        console.print(f"  SESSION {i + 1}/{len(records)}: {persona} x {task}")
        console.print(f"{'#' * 60}")

        if not session_id:
            console.print(
                "  WARNING: No target_session_id — cannot evaluate", style="yellow"
            )
            failed += 1
            continue

        if not metric_refs:
            console.print(
                "  WARNING: No metric_refs in run config — skipping evaluation",
                style="yellow",
            )
            failed += 1
            continue

        try:
            scenarios_by_id = {s.id: s for s in experiment.scenarios}
            scenario_obj = scenarios_by_id.get(task)
            persona_obj = personas_by_id.get(persona)
            fetch_result = fetch_by_session_id(
                session_id,
                langfuse,
                retry_timeout=langfuse_timeout,
                artifacts=record.artifacts_collected,
                task=scenario_obj,
                persona=persona_obj,
            )

            if not fetch_result.test_cases:
                console.print("  WARNING: No evaluable test cases", style="yellow")
                failed += 1
                continue

            eval_result = evaluate(fetch_result, metric_refs)
            eval_results.append(eval_result)

        except Exception as e:
            console.print(f"  WARNING: Evaluation failed: {e}", style="yellow")
            failed += 1

    if eval_results:
        from metis.engine.evaluation.types import EvalResult

        merged = EvalResult.merge(eval_results)
        reports_dir = experiment_dir / "reports"
        reports_dir.mkdir(exist_ok=True)

        scenarios_by_id = {s.id: s for s in experiment.scenarios}
        task_contexts: dict[str, TaskContext] = {}
        for record in records:
            sid = record.config.scenario
            if sid not in task_contexts:
                ctx: TaskContext = {"personas": []}
                scenario_obj = scenarios_by_id.get(sid)
                if scenario_obj:
                    ctx["description"] = scenario_obj.description
                    ctx["fixtures"] = scenario_obj.fixtures
                task_contexts[sid] = ctx
            persona_entry = {
                "id": record.config.persona,
                "stop_reason": record.outcome.stop_reason,
                "total_turns": record.outcome.total_turns,
                "duration_seconds": record.outcome.duration_seconds,
            }
            persona_obj = personas_by_id.get(record.config.persona)
            if persona_obj:
                persona_entry["description"] = persona_obj.description
            task_contexts[sid]["personas"].append(persona_entry)

        generate_report(
            merged,
            run_id="report",
            output_dir=reports_dir,
            experiment_description=experiment.description,
            task_contexts=task_contexts,
        )

    console.print(f"\n\n{'=' * 60}")
    console.print(f"  PIPELINE COMPLETE — {len(records)} run(s), {failed} failed")
    console.print(f"  Experiment: {experiment_dir}")
    console.print(f"{'=' * 60}")
