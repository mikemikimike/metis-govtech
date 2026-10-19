"""Tests for the ``metis engine simulate`` command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from metis.core.trials import TrialConfig, TrialOutcome, TrialRecord
from metis.engine import cli
from metis.engine.cli import app
from metis.engine.simulation import experiment as experiment_module

runner = CliRunner()

MINIMAL_EXPERIMENT = "schema_version: 2\nid: test-exp\nrunner_factory_ref: tests.unit.engine.test_runner_ref.StubRunnerFactory\npersonas:\n- id: alice\n  description: test persona\n  name: alice\nscenarios:\n- id: task-1\n  description: test scenario\n  name: task-1\ntarget:\n  name: Test target\n  users: Test users\n  description: Test target\ntasks:\n- id: TC-001\n  scenario_ref: task-1\n  persona_ref: alice\n  fixtures: []\n  num_trials: 1\n  behaviour_refs:\n  - EB-1\nfeatures:\n- id: F-1\n  name: Responses\n  description: Responses\n  behaviours:\n  - id: EB-1\n    name: Respond\n    description: Respond correctly\n    measured: true\n    criteria:\n    - id: AC-1-1\n      name: Check 1\n      description:\n        given: a request\n        when: the agent responds\n        then: the requirement is met\n      grader_fqn: tests.unit.engine.graders_for_tests.FixedScoreGrader\n      grader_args: {}\n"

TWO_TRIAL_EXPERIMENT = MINIMAL_EXPERIMENT.replace("num_trials: 1", "num_trials: 2")


def _write_source(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "specification.yaml").write_text(MINIMAL_EXPERIMENT)
    return input_dir


def _write_output(output_dir: Path, experiment_yaml: str = MINIMAL_EXPERIMENT) -> Path:
    """Create a resumable output directory with a frozen inputs/ snapshot."""
    (output_dir / "inputs" / "fixtures").mkdir(parents=True)
    (output_dir / "inputs" / "specification.yaml").write_text(experiment_yaml)
    return output_dir


def _write_record_marker(experiment_dir: Path) -> Path:
    record_path = (
        experiment_dir / "outputs" / "trials" / "TC-001-alice-1" / "record.json"
    )
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text("{}")
    return experiment_dir


def _write_record(
    experiment_dir: Path, folder: str, stop_reason: str = "goal_achieved"
) -> None:
    record = TrialRecord(
        config=TrialConfig(persona="alice", scenario="task-1"),
        outcome=TrialOutcome(
            stop_reason=stop_reason, total_turns=1, duration_seconds=1.0
        ),
    )
    path = experiment_dir / "outputs" / "trials" / folder / "record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json())


def _compact(value: str) -> str:
    return "".join(value.split())


def test_simulate_prints_evaluate_and_resume_handoff(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = _write_record_marker(tmp_path / "output")

    monkeypatch.setattr(cli, "_run_simulation", lambda *_a, **_k: experiment_dir)

    result = runner.invoke(app, ["simulate", "--input-dir", str(input_dir)])

    assert result.exit_code == 0
    compact_output = _compact(result.output)
    resolved = _compact(str(experiment_dir.resolve()))
    assert f"Specification:{resolved}" in compact_output
    assert f"Evaluate:metisengineevaluate--experiment-dir{resolved}" in compact_output
    assert (
        f"Resume:metisenginesimulate--resume--experiment-dir{resolved}"
        in compact_output
    )


def test_simulate_zero_records_exits_one(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = tmp_path / "output"
    experiment_dir.mkdir()
    monkeypatch.setattr(cli, "_run_simulation", lambda *_a, **_k: experiment_dir)

    result = runner.invoke(app, ["simulate", "--input-dir", str(input_dir)])

    assert result.exit_code == 1
    assert "No trial records found." in result.output
    assert "Evaluate:" not in result.output


def test_resume_runs_only_missing_or_system_error_records(
    monkeypatch, tmp_path: Path
) -> None:
    output_dir = _write_output(
        tmp_path / "experiments" / "execute" / "test-exp-20260101-010101",
        TWO_TRIAL_EXPERIMENT,
    )
    (output_dir / "inputs" / "fixtures" / "fixture.txt").write_text("frozen")
    _write_record(output_dir, "TC-001-alice-1", "goal_achieved")
    _write_record(output_dir, "TC-001-alice-2", "system_error")
    monkeypatch.setattr(cli, "_configure_process_logging", lambda *_a, **_k: None)
    selected: list[tuple[str, str, int]] = []

    def fake_execute_experiment(*_args: object, **kwargs: object) -> None:
        for scenario, persona, trial_index in kwargs["trial_plan"]:  # type: ignore[index]
            selected.append((scenario.id, persona.id, trial_index))

    monkeypatch.setattr(
        experiment_module, "execute_experiment", fake_execute_experiment
    )

    result = runner.invoke(
        app,
        ["simulate", "--resume", "--experiment-dir", str(output_dir), "--no-tui"],
    )

    assert result.exit_code == 0
    assert selected == [("task-1", "alice", 2)]
    assert "trials to redo" in " ".join(result.output.split())


def test_resume_passes_append_true_to_setup_engine_logging(
    monkeypatch, tmp_path: Path
) -> None:
    output_dir = _write_output(
        tmp_path / "experiments" / "execute" / "test-exp-20260101-010101",
        TWO_TRIAL_EXPERIMENT,
    )
    (output_dir / "inputs" / "fixtures" / "fixture.txt").write_text("frozen")
    _write_record(output_dir, "TC-001-alice-1", "goal_achieved")
    _write_record(output_dir, "TC-001-alice-2", "system_error")
    monkeypatch.setattr(cli, "_configure_process_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(experiment_module, "execute_experiment", lambda *_a, **_k: None)

    captured_append: list[object] = []
    _real_setup = cli.setup_engine_logging

    def _capturing_setup(*args: object, **kwargs: object) -> object:
        captured_append.append(kwargs.get("append"))
        return _real_setup(*args, **kwargs)

    monkeypatch.setattr(cli, "setup_engine_logging", _capturing_setup)

    result = runner.invoke(
        app,
        ["simulate", "--resume", "--experiment-dir", str(output_dir), "--no-tui"],
    )

    assert result.exit_code == 0
    assert captured_append == [True]


def test_resume_all_complete_is_noop(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_output(
        tmp_path / "experiments" / "execute" / "test-exp-20260101-010101"
    )
    (output_dir / "inputs" / "fixtures" / "fixture.txt").write_text("frozen")
    _write_record(output_dir, "TC-001-alice-1")
    monkeypatch.setattr(cli, "_configure_process_logging", lambda *_a, **_k: None)

    result = runner.invoke(
        app,
        ["simulate", "--resume", "--experiment-dir", str(output_dir), "--no-tui"],
    )

    assert result.exit_code == 0
    assert "nothing to resume" in result.output


def test_resume_directory_without_inputs_snapshot_exits_one(tmp_path: Path) -> None:
    output_dir = tmp_path / "experiments" / "execute" / "test-exp-20260101-010101"
    output_dir.mkdir(parents=True)

    result = runner.invoke(
        app,
        ["simulate", "--resume", "--experiment-dir", str(output_dir), "--no-tui"],
    )

    assert result.exit_code == 1
    assert "not a simulation output directory" in " ".join(result.output.split())


def test_resume_with_input_dir_lists_outputs_and_chooses_none(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = _write_source(tmp_path)
    root = tmp_path / "project"
    older = _write_output(root / "experiments" / "execute" / "test-exp-20260101-010101")
    newer = _write_output(root / "experiments" / "execute" / "test-exp-20260102-020202")
    monkeypatch.setattr(cli, "_find_project_root", lambda: root)

    result = runner.invoke(app, ["simulate", "--resume", "--input-dir", str(input_dir)])

    assert result.exit_code == 1
    compact_output = _compact(result.output)
    assert "--experiment-dir" in result.output
    assert _compact(str(older.resolve())) in compact_output
    assert _compact(str(newer.resolve())) in compact_output


@pytest.mark.parametrize("command", ["simulate", "run"])
@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ([], "pass --input-dir"),
        (["--input-dir", "in", "--experiment-dir", "out"], "not both"),
        (["--experiment-dir", "out"], "--experiment-dir needs --resume"),
        (["--resume", "--input-dir", "in"], "--resume needs --experiment-dir"),
    ],
)
def test_reject_invalid_path_options(
    command: str, extra: list[str], expected: str
) -> None:
    result = runner.invoke(app, [command, *extra, "--no-tui"])

    assert result.exit_code == 1
    assert expected in result.output
