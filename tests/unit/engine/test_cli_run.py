"""Tests for the ``metis engine run`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from metis.engine import cli
from metis.engine.cli import EvaluationOutcome, app

runner = CliRunner()

MINIMAL_EXPERIMENT = """\
schema_version: 2
id: test-exp
description: test experiment
runner_factory_ref: tests.unit.engine.test_runner_ref.StubRunnerFactory
personas:
  - id: alice
    description: test persona
scenarios:
  - id: task-1
    description: test scenario
    persona_refs: [alice]
"""


def _write_source(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "experiment.yaml").write_text(MINIMAL_EXPERIMENT)
    return input_dir


def _write_record_marker(experiment_dir: Path) -> Path:
    record_path = experiment_dir / "runs" / "task-1-alice-1" / "record.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text("{}")
    return experiment_dir


def test_run_composes_phases_and_prints_recovery_command(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = _write_record_marker(tmp_path / "experiment")
    phases: list[str] = []
    simulation_options: dict[str, object] = {}
    evaluation_paths: list[Path] = []
    evaluation_options: dict[str, object] = {}

    def fake_simulation(*_args: object, **kwargs: object) -> Path:
        phases.append("simulation")
        simulation_options.update(kwargs)
        return experiment_dir

    def fake_evaluation(path: Path, **kwargs: object) -> EvaluationOutcome:
        phases.append("evaluation")
        evaluation_paths.append(path)
        evaluation_options.update(kwargs)
        return EvaluationOutcome(1, 0, 1, False)

    monkeypatch.setattr(cli, "_run_simulation", fake_simulation)
    monkeypatch.setattr(cli, "_run_evaluation", fake_evaluation)

    result = runner.invoke(
        app,
        [
            "run",
            "--input-dir",
            str(input_dir),
            "--no-tui",
            "--langfuse-timeout",
            "120",
            "-v",
        ],
    )

    assert result.exit_code == 0
    assert phases == ["simulation", "evaluation"]
    assert simulation_options["no_tui"] is True
    assert simulation_options["resume"] is False
    assert evaluation_paths == [experiment_dir]
    assert evaluation_options == {
        "langfuse_timeout": 120,
        "verbose": 1,
        "quiet": False,
    }
    assert (
        f"Evaluate: metis engine evaluate --experiment-dir {experiment_dir.resolve()}"
        in result.output
    )
    assert (
        f"Resume: metis engine run --resume --experiment-dir {experiment_dir.resolve()}"
        in result.output
    )
    assert "PIPELINE COMPLETE" in result.output


def test_run_resume_evaluates_the_resumed_directory(
    monkeypatch, tmp_path: Path
) -> None:
    experiment_dir = _write_record_marker(tmp_path / "experiment")
    simulation_options: dict[str, object] = {}
    evaluation_paths: list[Path] = []

    def fake_simulation(*_args: object, **kwargs: object) -> Path:
        simulation_options.update(kwargs)
        return experiment_dir

    def fake_evaluation(path: Path, **_kwargs: object) -> EvaluationOutcome:
        evaluation_paths.append(path)
        return EvaluationOutcome(1, 1, 0, True)

    monkeypatch.setattr(cli, "_run_simulation", fake_simulation)
    monkeypatch.setattr(cli, "_run_evaluation", fake_evaluation)

    result = runner.invoke(
        app,
        ["run", "--resume", "--experiment-dir", str(experiment_dir), "--no-tui"],
    )

    assert result.exit_code == 0
    assert simulation_options["resume"] is True
    assert evaluation_paths == [experiment_dir]
    assert "PIPELINE COMPLETE" in result.output


def test_run_zero_simulation_records_exits_one(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    evaluation_called = False

    def fail_if_evaluated(*_args: object, **_kwargs: object) -> EvaluationOutcome:
        nonlocal evaluation_called
        evaluation_called = True
        raise AssertionError("evaluation should not run")

    monkeypatch.setattr(cli, "_run_simulation", lambda *_a, **_k: experiment_dir)
    monkeypatch.setattr(cli, "_run_evaluation", fail_if_evaluated)

    result = runner.invoke(app, ["run", "--input-dir", str(input_dir)])

    assert result.exit_code == 1
    assert not evaluation_called


def test_run_infrastructure_failure_prints_recovery_command(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = _write_record_marker(tmp_path / "experiment")
    monkeypatch.setattr(cli, "_run_simulation", lambda *_a, **_k: experiment_dir)

    def fail_evaluation(*_args: object, **_kwargs: object) -> EvaluationOutcome:
        raise RuntimeError("Langfuse unavailable")

    monkeypatch.setattr(cli, "_run_evaluation", fail_evaluation)

    result = runner.invoke(app, ["run", "--input-dir", str(input_dir)])

    assert result.exit_code != 0
    assert (
        f"Evaluate: metis engine evaluate --experiment-dir {experiment_dir.resolve()}"
        in result.output
    )
