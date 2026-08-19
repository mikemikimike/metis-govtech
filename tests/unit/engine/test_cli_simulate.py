"""Tests for the ``metis engine simulate`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from metis.engine import cli
from metis.engine.cli import app
from metis.engine.simulation import experiment as experiment_module
from metis.engine.simulation.types import RunConfig, RunOutcome, RunRecord

runner = CliRunner()

MINIMAL_EXPERIMENT = """\
schema_version: 1
id: test-exp
description: test experiment
personas:
  - id: alice
    description: test persona
scenarios:
  - id: task-1
    description: test scenario
    persona_refs: [alice]
"""

TWO_TRIAL_EXPERIMENT = MINIMAL_EXPERIMENT.replace(
    "    persona_refs: [alice]\n", "    persona_refs: [alice]\n    num_trials: 2\n"
)


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


def _write_record(
    experiment_dir: Path, folder: str, stop_reason: str = "goal_achieved"
) -> None:
    record = RunRecord(
        config=RunConfig(persona="alice", scenario="task-1"),
        outcome=RunOutcome(
            stop_reason=stop_reason, total_turns=1, duration_seconds=1.0
        ),
    )
    path = experiment_dir / "runs" / folder / "record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json())


def _compact(value: str) -> str:
    return "".join(value.split())


def test_simulate_prints_experiment_dir_handoff(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = _write_record_marker(tmp_path / "output")

    def fake_simulation(_input_dir: Path, **_kwargs: object) -> Path:
        return experiment_dir

    monkeypatch.setattr(cli, "_run_simulation", fake_simulation)

    result = runner.invoke(app, ["simulate", "--input-dir", str(input_dir)])

    assert result.exit_code == 0
    compact_output = _compact(result.output)
    assert f"Experiment:{_compact(str(experiment_dir))}" in compact_output
    assert (
        "Next:metisengineevaluate--experiment-dir"
        f"{_compact(str(experiment_dir.resolve()))}" in compact_output
    )


def test_simulate_zero_records_exits_one(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = tmp_path / "output"
    experiment_dir.mkdir()
    monkeypatch.setattr(
        cli, "_run_simulation", lambda *_args, **_kwargs: experiment_dir
    )

    result = runner.invoke(app, ["simulate", "--input-dir", str(input_dir)])

    assert result.exit_code == 1
    assert "No run records found." in result.output
    assert "Next:" not in result.output


def test_resume_runs_only_missing_or_system_error_records(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = _write_source(tmp_path)
    (input_dir / "experiment.yaml").write_text(TWO_TRIAL_EXPERIMENT)
    (input_dir / "fixtures").mkdir()
    (input_dir / "fixtures" / "fixture.txt").write_text("frozen")
    output_root = tmp_path / "project"
    output_dir = output_root / "experiments" / "test-exp-20260101-010101"
    (output_dir / "inputs" / "fixtures").mkdir(parents=True)
    (output_dir / "inputs" / "experiment.yaml").write_text(TWO_TRIAL_EXPERIMENT)
    (output_dir / "inputs" / "fixtures" / "fixture.txt").write_text("frozen")
    _write_record(output_dir, "task-1-alice-1", "goal_achieved")
    _write_record(output_dir, "task-1-alice-2", "system_error")
    monkeypatch.setattr(cli, "_find_project_root", lambda: output_root)
    monkeypatch.setattr(cli, "_configure_process_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(
        experiment_module.HarnessConfig,
        "load",
        classmethod(lambda cls, *_a, **_k: object()),
    )
    selected: list[tuple[str, str, int]] = []

    def fake_run_experiment(*_args: object, **kwargs: object) -> None:
        for scenario, persona, trial in kwargs["run_plan"]:  # type: ignore[index]
            selected.append((scenario.id, persona.id, trial))

    monkeypatch.setattr(experiment_module, "run_experiment", fake_run_experiment)

    result = runner.invoke(
        app, ["simulate", "--input-dir", str(input_dir), "--resume", "--no-tui"]
    )

    assert result.exit_code == 0
    assert selected == [("task-1", "alice", 1)]
    assert "1 runs to redo" in result.output


def test_resume_rejects_changed_fixture(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    (input_dir / "fixtures").mkdir()
    (input_dir / "fixtures" / "fixture.txt").write_text("current")
    output_root = tmp_path / "project"
    output_dir = output_root / "experiments" / "test-exp-20260101-010101"
    (output_dir / "inputs" / "fixtures").mkdir(parents=True)
    (output_dir / "inputs" / "experiment.yaml").write_text(MINIMAL_EXPERIMENT)
    (output_dir / "inputs" / "fixtures" / "fixture.txt").write_text("frozen")
    monkeypatch.setattr(cli, "_find_project_root", lambda: output_root)

    result = runner.invoke(
        app, ["simulate", "--input-dir", str(input_dir), "--resume", "--no-tui"]
    )

    assert result.exit_code == 1
    assert "fixtures differ from the frozen resume snapshot" in result.output


def test_resume_all_complete_is_noop(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    (input_dir / "fixtures").mkdir()
    (input_dir / "fixtures" / "fixture.txt").write_text("frozen")
    output_root = tmp_path / "project"
    output_dir = output_root / "experiments" / "test-exp-20260101-010101"
    (output_dir / "inputs" / "fixtures").mkdir(parents=True)
    (output_dir / "inputs" / "experiment.yaml").write_text(MINIMAL_EXPERIMENT)
    (output_dir / "inputs" / "fixtures" / "fixture.txt").write_text("frozen")
    _write_record(output_dir, "task-1-alice-1")
    monkeypatch.setattr(cli, "_find_project_root", lambda: output_root)

    result = runner.invoke(
        app, ["simulate", "--input-dir", str(input_dir), "--resume", "--no-tui"]
    )

    assert result.exit_code == 0
    assert "nothing to resume" in result.output


def test_resume_without_output_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    monkeypatch.setattr(cli, "_find_project_root", lambda: tmp_path / "project")

    result = runner.invoke(
        app, ["simulate", "--input-dir", str(input_dir), "--resume", "--no-tui"]
    )

    assert result.exit_code == 1
    assert "no simulation output found" in result.output
