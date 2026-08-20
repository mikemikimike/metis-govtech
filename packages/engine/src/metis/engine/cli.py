"""Command-line interface for metis-engine."""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import signal
import sys
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import typer
from dotenv import load_dotenv
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TaskID, TextColumn

from metis.core.console import console
from metis.engine import __version__
from metis.engine.logging import (
    EvaluationLogger,
    OrchestrationLogger,
    setup_engine_logging,
    teardown_engine_logging,
)
from metis.engine.tui import (
    SimulationRunState,
    SimulationScenarioState,
    SimulationState,
    TailBuffer,
    TUIContext,
)

if TYPE_CHECKING:
    from metis.engine.evaluation.types import EvalResult

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


def _format_final_summary(state: Any, experiment_dir: str, log_dir: str) -> str:
    """Build the static final summary printed after TUI exits."""
    total = state.total_runs
    completed = state.completed_runs
    reasons = [r.stop_reason for sc in state.scenarios for r in sc.runs]
    achieved = sum(1 for r in reasons if r == "goal_achieved")
    abandoned = sum(1 for r in reasons if r == "user_abandoned")
    timed_out = sum(1 for r in reasons if r == "timeout")
    # Remaining completed runs (e.g. system_error, max_turns) count as errors.
    errored = completed - achieved - abandoned - timed_out

    elapsed = state.elapsed_seconds
    h = int(elapsed) // 3600
    m = (int(elapsed) % 3600) // 60

    elapsed_str = f"{h}h {m:02d}m" if h > 0 else f"{m}m"

    lines = [
        f"METIS {state.experiment_id} — completed in {elapsed_str}",
        f"Simulation: {completed}/{total} runs "
        f"({achieved} goal achieved, {abandoned} abandoned, "
        f"{timed_out} timeout, {errored} error)",
        f"Logs:   {log_dir}/",
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class EvaluationOutcome:
    """Summary returned by the evaluation phase."""

    total_records: int
    successful_records: int
    failed_records: int
    report_written: bool


class EvaluationInputError(RuntimeError):
    """Raised when an experiment snapshot or run record is invalid."""


def _resolve_log_level(verbose: int, quiet: bool) -> str:
    """Resolve the CLI log level."""
    if quiet:
        return "ERROR"
    if verbose >= 2:
        return "DEBUG"
    if verbose >= 1:
        return "INFO"
    return "WARNING"


def _configure_process_logging(log_level: str, *, use_tui: bool = False) -> None:
    """Configure structured logging before importing engine modules."""
    from metis.core.logging import configure_logging

    configure_logging(level="DEBUG" if use_tui else log_level)

    # Module-level loggers cache their processor chain. Disable that cache so
    # the simulation log router can be installed after these imports.
    import structlog

    structlog.configure(cache_logger_on_first_use=False)


def _record_files(experiment_dir: Path) -> list[Path]:
    """Return run records in the same order used by the old CLI."""
    return sorted(
        experiment_dir.glob("runs/*/record.json"), key=lambda path: path.stat().st_mtime
    )


def _resolve_latest_experiment(input_dir: Path) -> Path:
    """Resolve the newest output for the experiment in ``input_dir``.

    Used by ``simulate --resume``, which continues the last run for an
    experiment. ``evaluate`` deliberately does not use this: it takes an
    explicit ``--experiment-dir`` so the scored output never depends on
    timestamps.
    """
    from metis.engine.simulation.types import Experiment

    resolved_input_dir = input_dir.resolve()
    if not resolved_input_dir.is_dir():
        console.print(
            f"Error: input directory '{resolved_input_dir}' does not exist",
            style="bold red",
        )
        raise EvaluationInputError("invalid input directory")
    experiment_path = resolved_input_dir / "experiment.yaml"
    if not experiment_path.exists():
        console.print(
            f"Error: missing required file 'experiment.yaml' in {resolved_input_dir}",
            style="bold red",
        )
        raise EvaluationInputError("invalid input directory")
    try:
        experiment = Experiment.load_file(experiment_path)
    except Exception as exc:
        console.print(f"Error: failed to load experiment.yaml: {exc}", style="bold red")
        raise EvaluationInputError("failed to load input experiment") from exc

    experiments_root = _find_project_root() / "experiments"
    pattern = re.compile(
        rf"^{re.escape(experiment.id)}-(?P<timestamp>\d{{8}}-\d{{6}})$"
    )
    candidates: list[tuple[datetime, Path]] = []
    if experiments_root.is_dir():
        for candidate in experiments_root.iterdir():
            if not candidate.is_dir():
                continue
            match = pattern.fullmatch(candidate.name)
            if not match:
                continue
            try:
                timestamp = datetime.strptime(match.group("timestamp"), "%Y%m%d-%H%M%S")
            except ValueError:
                continue
            candidates.append((timestamp, candidate))

    if not candidates:
        console.print(
            f"Error: no simulation output found for experiment '{experiment.id}' "
            f"under {experiments_root}",
            style="bold red",
        )
        raise EvaluationInputError("no matching experiment output")

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1].resolve()


def _resolve_experiment_dir(experiment_dir: Path) -> Path:
    """Validate an explicit simulation output directory."""
    resolved = experiment_dir.resolve()
    if not resolved.is_dir():
        console.print(
            f"Error: experiment directory '{resolved}' does not exist",
            style="bold red",
        )
        raise EvaluationInputError("invalid experiment directory")
    if not (resolved / "inputs").is_dir():
        console.print(
            f"Error: '{resolved}' is not a simulation output directory "
            "(no 'inputs/' snapshot). Run 'metis engine simulate' first.",
            style="bold red",
        )
        raise EvaluationInputError("invalid experiment directory")
    return resolved


def _evaluate_command(experiment_dir: Path) -> str:
    """Build the shell-safe command for evaluating a simulation output."""
    return shlex.join(
        ["metis", "engine", "evaluate", "--experiment-dir", str(experiment_dir)]
    )


def _print_evaluate_handoff(experiment_dir: Path) -> None:
    """Print the command that evaluates a completed simulation."""
    console.print(f"Experiment: {experiment_dir}")
    console.print(
        f"Next: {_evaluate_command(experiment_dir.resolve())}",
        no_wrap=True,
        overflow="ignore",
        crop=False,
        soft_wrap=True,
    )


def _print_evaluation_summary(
    experiment_dir: Path, outcome: EvaluationOutcome, *, pipeline: bool
) -> None:
    """Print the final summary for standalone evaluation or the combined run."""
    label = "PIPELINE COMPLETE" if pipeline else "EVALUATION COMPLETE"
    console.print(f"\n\n{'=' * 60}")
    console.print(
        f"  {label} — {outcome.total_records} run(s), {outcome.failed_records} failed"
    )
    console.print(f"  Experiment: {experiment_dir}")
    console.print(f"  Log: {experiment_dir / 'logs' / 'evaluate.log'}")
    console.print(f"{'=' * 60}")


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    """Return a byte snapshot of a directory tree, including directories."""
    if not root.exists():
        return {}
    snapshot: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = None
        elif path.is_file():
            snapshot[relative] = path.read_bytes()
        else:
            snapshot[relative] = b"<unsupported-file-type>"
    return snapshot


def _validate_resume_snapshot(input_dir: Path, experiment_dir: Path) -> None:
    """Require source YAML and fixtures to match the frozen snapshot."""
    current_yaml = input_dir / "experiment.yaml"
    frozen_yaml = experiment_dir / "inputs" / "experiment.yaml"
    try:
        yaml_matches = current_yaml.read_bytes() == frozen_yaml.read_bytes()
    except OSError:
        yaml_matches = False
    if not yaml_matches:
        console.print(
            "Error: experiment.yaml differs from the frozen resume snapshot; "
            "start a new simulation if the change was intentional.",
            style="bold red",
        )
        raise EvaluationInputError("experiment snapshot differs")

    current_fixtures = _tree_snapshot(input_dir / "fixtures")
    frozen_fixtures = _tree_snapshot(experiment_dir / "inputs" / "fixtures")
    if current_fixtures != frozen_fixtures:
        console.print(
            "Error: fixtures differ from the frozen resume snapshot; "
            "start a new simulation if the change was intentional.",
            style="bold red",
        )
        raise EvaluationInputError("fixture snapshot differs")


def _classify_resume_runs(
    experiment_dir: Path,
    run_plan: list[Any],
) -> tuple[list[Any], dict[tuple[str, str, int], Any]]:
    """Return redo items and valid existing records keyed by plan identity."""
    from metis.engine.simulation.experiment import run_folder_name
    from metis.engine.simulation.types import RunRecord

    redo: list[Any] = []
    complete: dict[tuple[str, str, int], Any] = {}
    for scenario, persona, trial in run_plan:
        record_path = (
            experiment_dir
            / "runs"
            / run_folder_name(scenario, persona, trial)
            / "record.json"
        )
        try:
            record = RunRecord.load_file(record_path)
        except Exception:
            redo.append((scenario, persona, trial))
            continue
        key = (scenario.id, persona.id, trial + 1)
        if record.outcome.stop_reason == "system_error":
            redo.append((scenario, persona, trial))
        else:
            complete[key] = record
    return redo, complete


def _run_simulation(
    input_dir: Path,
    *,
    verbose: int,
    quiet: bool,
    no_tui: bool,
    log_format: Literal["text", "json"],
    log_dir: Path | None,
    concurrency: int,
    resume: bool = False,
) -> Path:
    """Run simulation and return its experiment directory."""
    load_dotenv()
    use_tui = not no_tui and sys.stderr.isatty()
    log_level = _resolve_log_level(verbose, quiet)

    # Configure logging before importing harness modules. They create
    # module-level loggers that cache the processor chain.
    _configure_process_logging(log_level, use_tui=use_tui)

    from metis.engine.simulation.experiment import (
        HarnessConfig,
        expand_run_plan,
        run_experiment,
    )
    from metis.engine.simulation.types import Experiment

    if not os.environ.get("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"):
        os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "300"

    project_root = _find_project_root()
    resolved_input_dir = input_dir.resolve()
    _validate_inputs(resolved_input_dir)

    experiment_path = resolved_input_dir / "experiment.yaml"
    source_experiment = Experiment.load_file(experiment_path)

    if resume:
        try:
            experiment_dir = _resolve_latest_experiment(resolved_input_dir)
        except EvaluationInputError:
            raise typer.Exit(code=1) from None
        try:
            _validate_resume_snapshot(resolved_input_dir, experiment_dir)
        except EvaluationInputError:
            raise typer.Exit(code=1) from None
        experiment = Experiment.load_file(experiment_dir / "inputs" / "experiment.yaml")
        fixtures_dir = experiment_dir / "inputs" / "fixtures"
    else:
        experiment = source_experiment
        fixtures_dir = resolved_input_dir / "fixtures"
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        experiment_dir = project_root / "experiments" / f"{experiment.id}-{suffix}"
        experiment_dir.mkdir(parents=True)
        shutil.copytree(resolved_input_dir, experiment_dir / "inputs")

    personas_by_id = {persona.id: persona for persona in experiment.personas}
    run_plan = expand_run_plan(experiment, personas_by_id)
    if resume:
        redo_plan, complete_records = _classify_resume_runs(experiment_dir, run_plan)
        console.print(
            f"Resume plan: {experiment_dir} — {len(redo_plan)} runs to redo, "
            f"{len(complete_records)} already complete"
        )
        if not redo_plan:
            console.print("nothing to resume")
            return experiment_dir
    else:
        redo_plan = run_plan
        complete_records = {}

    config = HarnessConfig.load()
    headed = os.environ.get("HEADED", "").lower() == "true"

    console.print(f"\n{'=' * 60}")
    console.print("  SIMULATION")
    console.print(f"{'=' * 60}")
    console.print(f"  Experiment: {experiment_dir}")
    console.print(f"  Input: {resolved_input_dir}")
    console.print(f"  Mode: {'headed' if headed else 'headless'}\n")

    resolved_log_dir = log_dir or (experiment_dir / "logs")
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    scenarios_state: list[SimulationScenarioState] = []
    total_run_count = 0
    for scenario in experiment.scenarios:
        run_states: list[SimulationRunState] = []
        for persona_ref in scenario.persona_refs:
            for trial_idx in range(scenario.num_trials):
                total_run_count += 1
                run_states.append(
                    SimulationRunState(
                        scenario_id=scenario.id,
                        persona_id=persona_ref,
                        trial=trial_idx + 1,
                        num_trials=scenario.num_trials,
                        phase="pending",
                        current_turn=None,
                        max_turns=20,
                        turn_detail="",
                        duration_seconds=None,
                        stop_reason=None,
                    )
                )
        scenarios_state.append(
            SimulationScenarioState(
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

    for (scenario_id, persona_id, trial), record in complete_records.items():
        sim_state.complete_run(
            scenario_id,
            persona_id,
            trial=trial,
            stop_reason=record.outcome.stop_reason,
            duration_seconds=record.outcome.duration_seconds,
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
        log_dir=resolved_log_dir, log_format=log_format, append=resume
    )
    if resume:
        orchestration_logger.resume_started(len(redo_plan), len(complete_records))

    tui_ctx: TUIContext | None = None
    if use_tui:
        tui_ctx = TUIContext(state=sim_state, tail_buffers=tail_buffers)

    interrupt_count = 0
    interrupt_lock = threading.Lock()
    shutdown_event = threading.Event()

    def _handle_sigint(_signum: int, _frame: Any) -> None:
        nonlocal interrupt_count
        with interrupt_lock:
            interrupt_count += 1
            if interrupt_count >= 2:
                if not use_tui:
                    console.print("\nForce abort.", style="bold red")
                sys.exit(130)
            shutdown_event.set()
            if not use_tui:
                console.print(
                    "\nInterrupt received — finishing current run. "
                    "No new runs will start. Press Ctrl+C again to force abort.",
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
                run_plan=redo_plan,
                state=sim_state,
                orchestration_logger=orchestration_logger,
                log_router=log_router,
                tui_ctx=tui_ctx,
                shutdown_event=shutdown_event,
            )
    finally:
        signal.signal(signal.SIGINT, prev_handler)
        teardown_engine_logging(log_router)
        orchestration_logger.close()

    console.print(
        _format_final_summary(
            sim_state,
            str(experiment_dir),
            str(resolved_log_dir),
        )
    )
    if shutdown_event.is_set():
        raise typer.Exit(code=130)
    return experiment_dir


def _load_evaluation_experiment(experiment_dir: Path) -> Any:
    """Validate and load the frozen experiment snapshot."""
    from metis.engine.simulation.types import Experiment

    inputs_dir = experiment_dir / "inputs"
    if not inputs_dir.is_dir():
        console.print(
            f"Error: missing required file 'experiment.yaml' in {inputs_dir}",
            style="bold red",
        )
        raise EvaluationInputError("missing experiment snapshot")

    try:
        _validate_inputs(inputs_dir)
    except SystemExit as exc:
        raise EvaluationInputError(
            f"invalid experiment snapshot in {inputs_dir}"
        ) from exc

    try:
        return Experiment.load_file(inputs_dir / "experiment.yaml")
    except Exception as exc:
        console.print(
            f"Error: failed to load experiment snapshot: {exc}", style="bold red"
        )
        raise EvaluationInputError("failed to load experiment snapshot") from exc


def _create_evaluation_progress() -> Progress:
    """Create the standard, non-full-screen evaluation progress bar."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    )


def _update_evaluation_progress(
    progress: Progress | None,
    task_id: TaskID | None,
    *,
    record_number: int,
    total_records: int,
    label: str,
    phase: str,
    advance: int = 0,
) -> None:
    """Update the progress bar or print one linear progress message."""
    description = f"{label} — {phase}"
    if progress and task_id is not None:
        progress.update(task_id, description=description, advance=advance)
    else:
        console.print(f"Evaluation {record_number}/{total_records}: {description}")


def _log_metric_results(
    evaluation_log: EvaluationLogger,
    eval_result: EvalResult,
    *,
    record_label: str,
) -> None:
    """Write complete metric outputs for every evaluated test case."""
    metric_outputs: list[dict[str, object]] = []

    def _collect(scope: str, test_case: object, metric_results: list) -> None:
        test_case_name = getattr(test_case, "name", None)
        for metric_result in metric_results:
            metric_outputs.append(
                {
                    "record": record_label,
                    "scope": scope,
                    "test_case": test_case_name,
                    "metric": metric_result.name,
                    "score": metric_result.score,
                    "success": metric_result.success,
                    "skipped": metric_result.skipped,
                    "reason": metric_result.reason,
                    "evaluation_cost": metric_result.evaluation_cost,
                    "input_tokens": metric_result.input_tokens,
                    "output_tokens": metric_result.output_tokens,
                }
            )

    for turn_result in eval_result.turn_results:
        _collect("turn", turn_result.llm_test_case, turn_result.metric_results)
    for session_result in eval_result.session_results:
        _collect(
            "session",
            session_result.conversational_test_case,
            session_result.metric_results,
        )

    for metric_output in metric_outputs:
        evaluation_log.write(
            "METRIC RESULT — "
            + json.dumps(metric_output, ensure_ascii=False, default=str)
        )
    evaluation_log.write(
        f"METRIC RESULTS — record={record_label} count={len(metric_outputs)}"
    )


def _run_evaluation(
    experiment_dir: Path,
    *,
    langfuse_timeout: int,
    verbose: int,
    quiet: bool,
) -> EvaluationOutcome:
    """Evaluate records in an existing experiment directory."""
    load_dotenv()
    log_level = _resolve_log_level(verbose, quiet)
    _configure_process_logging(log_level)
    evaluation_log = EvaluationLogger(experiment_dir / "logs")
    evaluation_log.write(f"EVALUATION STARTED — {experiment_dir}")

    from metis.engine.evaluation import evaluate as evaluate_metrics
    from metis.engine.evaluation.types import EvalResult
    from metis.engine.extractor import fetch_by_session_id, get_langfuse_client
    from metis.engine.reporting import PersonaContext, TaskContext, generate_report
    from metis.engine.simulation.types import RunRecord

    if not os.environ.get("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"):
        os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "300"

    experiment = _load_evaluation_experiment(experiment_dir)
    files = _record_files(experiment_dir)
    if not files:
        evaluation_log.write("EVALUATION COMPLETED — 0 records")
        return EvaluationOutcome(0, 0, 0, False)

    try:
        records: list[RunRecord] = [RunRecord.load_file(path) for path in files]
    except Exception as exc:
        console.print(f"Error: failed to load run record: {exc}", style="bold red")
        raise EvaluationInputError("failed to load run record") from exc

    console.print(f"  Loaded {len(records)} run record(s)")
    evaluation_log.write(f"LOADED {len(records)} run record(s)")
    langfuse = get_langfuse_client()
    personas_by_id = {persona.id: persona for persona in experiment.personas}
    scenarios_by_id = {scenario.id: scenario for scenario in experiment.scenarios}
    eval_results: list[EvalResult] = []
    failed = 0
    interactive_progress = sys.stderr.isatty()
    progress = _create_evaluation_progress() if interactive_progress else None

    with progress if progress else nullcontext():
        task_id = (
            progress.add_task("Evaluation", total=len(records)) if progress else None
        )
        for index, record in enumerate(records):
            session_id = record.target_session_id
            persona_id = record.config.persona
            scenario_id = record.config.scenario
            metric_refs = record.config.metric_refs
            label = f"{persona_id} x {scenario_id}"
            record_failed = False
            failure_reason: str | None = None

            evaluation_log.write(
                f"RECORD {index + 1}/{len(records)} {label} — EXTRACTING"
            )
            _update_evaluation_progress(
                progress,
                task_id,
                record_number=index + 1,
                total_records=len(records),
                label=label,
                phase="extracting",
            )

            console.print(f"\n\n{'#' * 60}")
            console.print(f"  SESSION {index + 1}/{len(records)}: {label}")
            console.print(f"{'#' * 60}")

            try:
                if not session_id:
                    console.print(
                        "  WARNING: No target_session_id — cannot evaluate",
                        style="yellow",
                    )
                    failed += 1
                    record_failed = True
                    failure_reason = "No target_session_id"
                    continue

                if not metric_refs:
                    console.print(
                        "  WARNING: No metric_refs in run config — skipping evaluation",
                        style="yellow",
                    )
                    failed += 1
                    record_failed = True
                    failure_reason = "No metric_refs in run config"
                    continue

                try:
                    fetch_result = fetch_by_session_id(
                        session_id,
                        langfuse,
                        retry_timeout=langfuse_timeout,
                        artifacts=record.artifacts_collected,
                        scenario=scenarios_by_id.get(scenario_id),
                        persona=personas_by_id.get(persona_id),
                        stop_reason=record.outcome.stop_reason,
                        cancellation_available=True,
                    )

                    if not fetch_result.test_cases:
                        console.print(
                            "  WARNING: No evaluable test cases", style="yellow"
                        )
                        failed += 1
                        record_failed = True
                        failure_reason = "No evaluable test cases"
                        continue

                    evaluation_log.write(
                        f"RECORD {index + 1}/{len(records)} {label} — EVALUATING"
                    )
                    for metric_ref in metric_refs:
                        evaluation_log.write(
                            "METRIC CONFIG — "
                            + json.dumps(
                                {
                                    "record": label,
                                    "fqn": metric_ref.fqn,
                                    "args": metric_ref.args,
                                },
                                ensure_ascii=False,
                                default=str,
                                sort_keys=True,
                            )
                        )
                    _update_evaluation_progress(
                        progress,
                        task_id,
                        record_number=index + 1,
                        total_records=len(records),
                        label=label,
                        phase="evaluating",
                    )
                    eval_result = evaluate_metrics(fetch_result, metric_refs)
                    eval_results.append(eval_result)
                    _log_metric_results(
                        evaluation_log,
                        eval_result,
                        record_label=label,
                    )
                except Exception as exc:
                    console.print(
                        f"  WARNING: Evaluation failed: {exc}", style="yellow"
                    )
                    failed += 1
                    record_failed = True
                    failure_reason = str(exc)
            finally:
                terminal_phase = "failed" if record_failed else "done"
                log_suffix = f"FAILED — {failure_reason}" if record_failed else "DONE"
                evaluation_log.write(
                    f"RECORD {index + 1}/{len(records)} {label} — {log_suffix}"
                )
                _update_evaluation_progress(
                    progress,
                    task_id,
                    record_number=index + 1,
                    total_records=len(records),
                    label=label,
                    phase=terminal_phase,
                    advance=1,
                )

        if progress and task_id is not None:
            progress.update(task_id, description="Evaluation complete")

    report_written = False
    if eval_results:
        merged = EvalResult.merge(eval_results)
        reports_dir = experiment_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        task_contexts: dict[str, TaskContext] = {}
        for record in records:
            scenario_id = record.config.scenario
            if scenario_id not in task_contexts:
                context: TaskContext = {"personas": []}
                scenario_obj = scenarios_by_id.get(scenario_id)
                if scenario_obj:
                    context["description"] = scenario_obj.description
                    context["fixtures"] = scenario_obj.fixtures
                task_contexts[scenario_id] = context

            persona_entry: PersonaContext = {
                "id": record.config.persona,
                "stop_reason": record.outcome.stop_reason,
                "total_turns": record.outcome.total_turns,
                "duration_seconds": record.outcome.duration_seconds,
            }
            persona_obj = personas_by_id.get(record.config.persona)
            if persona_obj:
                persona_entry["description"] = persona_obj.description
            task_contexts[scenario_id].setdefault("personas", []).append(persona_entry)

        generate_report(
            merged,
            run_id="report",
            output_dir=reports_dir,
            experiment_description=experiment.description,
            task_contexts=task_contexts,
        )
        report_written = True
        evaluation_log.write(f"REPORT WRITTEN — {reports_dir}")

    outcome = EvaluationOutcome(
        total_records=len(records),
        successful_records=len(eval_results),
        failed_records=failed,
        report_written=report_written,
    )
    evaluation_log.write(
        "EVALUATION COMPLETED — "
        f"{outcome.successful_records}/{outcome.total_records} records succeeded, "
        f"{outcome.failed_records} failed"
    )
    return outcome


def _run_evaluation_command(
    experiment_dir: Path,
    *,
    langfuse_timeout: int,
    verbose: int,
    quiet: bool,
) -> EvaluationOutcome:
    """Run evaluation and convert expected input errors to a CLI exit."""
    try:
        return _run_evaluation(
            experiment_dir,
            langfuse_timeout=langfuse_timeout,
            verbose=verbose,
            quiet=quiet,
        )
    except EvaluationInputError as exc:
        EvaluationLogger(experiment_dir / "logs", reset=False).write(
            f"EVALUATION FAILED — {exc}"
        )
        raise typer.Exit(code=1) from None
    except Exception as exc:
        EvaluationLogger(experiment_dir / "logs", reset=False).write(
            f"EVALUATION FAILED — {exc}"
        )
        console.print(f"Error: evaluation failed: {exc}", style="bold red")
        raise typer.Exit(code=1) from exc


@app.command()
def simulate(
    input_dir: Path = typer.Option(
        ..., "--input-dir", help="Directory containing experiment.yaml and fixtures/"
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
    resume: bool = typer.Option(
        False, "--resume", help="Resume the newest existing simulation output"
    ),
) -> None:
    """Run simulation only and prepare the evaluation handoff."""
    experiment_dir = _run_simulation(
        input_dir,
        verbose=verbose,
        quiet=quiet,
        no_tui=no_tui,
        log_format=log_format,
        log_dir=log_dir,
        concurrency=concurrency,
        resume=resume,
    )
    if not _record_files(experiment_dir):
        console.print("No run records found.", style="bold red")
        raise typer.Exit(code=1)
    _print_evaluate_handoff(experiment_dir)


@app.command()
def evaluate(
    experiment_dir: Path = typer.Option(
        ...,
        "--experiment-dir",
        help=(
            "Output directory that simulate created, "
            "e.g. experiments/my-eval-20260820-143000/"
        ),
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
) -> None:
    """Evaluate one simulation output directory."""
    try:
        resolved_experiment_dir = _resolve_experiment_dir(experiment_dir)
    except EvaluationInputError:
        raise typer.Exit(code=1) from None
    console.print(f"Selected experiment: {resolved_experiment_dir}")
    outcome = _run_evaluation_command(
        resolved_experiment_dir,
        langfuse_timeout=langfuse_timeout,
        verbose=verbose,
        quiet=quiet,
    )
    if outcome.total_records == 0:
        console.print("nothing to evaluate")
    _print_evaluation_summary(resolved_experiment_dir, outcome, pipeline=False)


@app.command()
def run(
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
    resume: bool = typer.Option(
        False, "--resume", help="Resume the newest existing simulation output"
    ),
) -> None:
    """Run simulation followed by evaluation and report generation."""
    experiment_dir = _run_simulation(
        input_dir,
        verbose=verbose,
        quiet=quiet,
        no_tui=no_tui,
        log_format=log_format,
        log_dir=log_dir,
        concurrency=concurrency,
        resume=resume,
    )
    if not _record_files(experiment_dir):
        console.print("No run records found.", style="bold red")
        raise typer.Exit(code=1)

    try:
        outcome = _run_evaluation_command(
            experiment_dir,
            langfuse_timeout=langfuse_timeout,
            verbose=verbose,
            quiet=quiet,
        )
    except Exception:
        _print_evaluate_handoff(experiment_dir)
        raise

    if outcome.failed_records:
        _print_evaluate_handoff(experiment_dir)
    _print_evaluation_summary(experiment_dir, outcome, pipeline=True)
