"""Command-line interface for metis-engine."""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import typer
from dotenv import load_dotenv

from metis.core.console import console
from metis.engine import __version__

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

    seen_tasks: set[str] = set()
    for task in experiment.tasks:
        if task.id in seen_tasks:
            console.print(
                f"Error: duplicate task id '{task.id}' in experiment.yaml",
                style="bold red",
            )
            sys.exit(1)
        seen_tasks.add(task.id)

    defined_personas = {p.id for p in experiment.personas}
    for task in experiment.tasks:
        for ref in task.persona_refs:
            if ref not in defined_personas:
                available = ", ".join(sorted(defined_personas))
                console.print(
                    f"Error: task '{task.id}' references unknown persona '{ref}' (available: {available})",
                    style="bold red",
                )
                sys.exit(1)

    fixtures_dir = input_dir / "fixtures"
    for task in experiment.tasks:
        for fixture in task.fixtures:
            if not (fixtures_dir / fixture).exists():
                console.print(
                    f"Error: task '{task.id}' references fixture '{fixture}' which does not exist in {fixtures_dir}",
                    style="bold red",
                )
                sys.exit(1)

    for task in experiment.tasks:
        for metric_ref in task.metric_refs:
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
) -> None:
    """Run end-to-end simulation, evaluation, and report."""
    import os

    from metis.core.logging import configure_logging
    from metis.engine.evaluation import evaluate
    from metis.engine.extractor import fetch_by_session_id, get_langfuse_client
    from metis.engine.reporting import generate_report
    from metis.engine.simulation.harness import HarnessConfig, run_experiment
    from metis.engine.simulation.types import Experiment, SessionRecord

    load_dotenv()

    if verbose >= 2:
        log_level = "DEBUG"
    elif verbose >= 1:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    configure_logging(level=log_level)

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

    run_experiment(
        config=config,
        experiment=experiment,
        personas_by_id=personas_by_id,
        output_dir=experiment_dir,
        fixtures_dir=fixtures_dir,
        headed=headed,
    )

    files = sorted(
        experiment_dir.glob("sessions/*/record.json"), key=lambda p: p.stat().st_mtime
    )
    records: list[SessionRecord] = [SessionRecord.load_file(f) for f in files]

    if not records:
        console.print("No session records found.")
        sys.exit(1)

    console.print(f"  Loaded {len(records)} session record(s)")

    langfuse = get_langfuse_client()
    eval_results = []
    failed = 0

    for i, record in enumerate(records):
        session_id = record.target_session_id
        persona = record.config.persona
        task = record.config.task
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
                "  WARNING: No metric_refs in session config — skipping evaluation",
                style="yellow",
            )
            failed += 1
            continue

        try:
            tasks_by_id = {t.id: t for t in experiment.tasks}
            task_obj = tasks_by_id.get(task)
            persona_obj = personas_by_id.get(persona)
            fetch_result = fetch_by_session_id(
                session_id,
                langfuse,
                retry_timeout=langfuse_timeout,
                artifacts=record.artifacts_collected,
                task=task_obj,
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
        generate_report(
            merged,
            run_id="report",
            output_dir=reports_dir,
            experiment_description=experiment.description,
        )

    console.print(f"\n\n{'=' * 60}")
    console.print(f"  PIPELINE COMPLETE — {len(records)} session(s), {failed} failed")
    console.print(f"  Experiment: {experiment_dir}")
    console.print(f"{'=' * 60}")
