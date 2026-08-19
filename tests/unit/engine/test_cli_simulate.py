"""Tests for the ``metis engine simulate`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from metis.engine import cli
from metis.engine.cli import app

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


def _compact(value: str) -> str:
    return "".join(value.split())


def test_simulate_prints_input_handoff(monkeypatch, tmp_path: Path) -> None:
    input_dir = _write_source(tmp_path)
    experiment_dir = _write_record_marker(tmp_path / "output")

    def fake_simulation(_input_dir: Path, **_kwargs: object) -> Path:
        return experiment_dir

    monkeypatch.setattr(cli, "_run_simulation", fake_simulation)

    result = runner.invoke(app, ["simulate", "--input-dir", str(input_dir)])

    assert result.exit_code == 0
    compact_output = _compact(result.output)
    assert "metisengineevaluate--input-dir" in compact_output
    assert _compact(str(input_dir.resolve())) in compact_output


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
