"""Tests for the ``metis insights report`` command."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from metis.core.report import Report
from metis.insights._legacy_results import (
    EvaluationResults,
    TurnGraderResult,
    TurnReport,
)
from metis.insights.cli import app

runner = CliRunner()

SPECIFICATION = "schema_version: 2\nid: test-exp\nrunner_factory_ref: tests.unit.engine.test_runner_ref.StubRunnerFactory\npersonas:\n- id: alice\n  description: test persona\n  name: alice\nscenarios:\n- id: task-1\n  description: test scenario\n  name: task-1\ntarget:\n  name: Test target\n  users: Test users\n  description: Test target\ntasks:\n- id: TC-001\n  scenario_ref: task-1\n  persona_ref: alice\n  fixtures: []\n  num_trials: 1\n  behaviour_refs:\n  - EB-1\nfeatures:\n- id: F-1\n  name: Responses\n  description: Responses\n  behaviours:\n  - id: EB-1\n    name: Respond\n    description: Respond correctly\n    measured: true\n    criteria:\n    - id: AC-1-1\n      name: Check 1\n      description:\n        given: a request\n        when: the agent responds\n        then: the requirement is met\n      grader_fqn: metis.library.graders.TurnBudgetGrader\n      grader_args: {}\n"


def _compact(value: str) -> str:
    return "".join(value.split())


def _results(*, success: bool = True) -> EvaluationResults:
    return EvaluationResults(
        run_id="report",
        turn_results=[
            TurnReport(
                trace_id="t-1",
                session_id="session-1",
                scenario_id="task-1",
                turn_index=0,
                total_turns=1,
                input="hi",
                output="hello",
                routed_to="direct",
                graders=[
                    TurnGraderResult(
                        criterion_id="AC-1-1",
                        grader_fqn="metis.library.graders.TurnBudgetGrader",
                        task_id="TC-001",
                        trial_index=1,
                        name="TurnBudgetGrader",
                        score=1.0 if success else 0.0,
                        reason="ok",
                        success=success,
                        skipped=False,
                    )
                ],
            )
        ],
        routing={
            "total_traces": 1,
            "total_sessions": 1,
            "direct_handle": 1,
            "routing_failed": 0,
            "subagent_counts": {},
        },
        timings={"turn_graders_seconds": 1.0, "session_graders_seconds": 0.0},
        latency_seconds=1.0,
    )


def _write_experiment(root: Path, *, with_specification: bool = True) -> Path:
    """Write an evaluated experiment directory; return its results.json path."""
    experiment_dir = root / "experiments" / "execute" / "test-exp-20260101-010101"
    if with_specification:
        (experiment_dir / "inputs").mkdir(parents=True)
        (experiment_dir / "inputs" / "specification.yaml").write_text(
            SPECIFICATION, encoding="utf-8"
        )
    results_file = experiment_dir / "outputs" / "reports" / "results.json"
    _results().save(results_file)
    return results_file


def test_report_writes_report_files_beside_results(tmp_path: Path) -> None:
    results_file = _write_experiment(tmp_path)

    result = runner.invoke(app, ["report", "--results-file", str(results_file)])

    assert result.exit_code == 0, result.output
    reports_dir = results_file.parent
    report = json.loads((reports_dir / "report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    assert Report.model_validate(report).target == "Test target"
    without_version = {
        key: value for key, value in report.items() if key != "schema_version"
    }
    assert Report.model_validate(without_version).schema_version == 2
    for unsupported_version in (1, 3, None):
        invalid = {**report, "schema_version": unsupported_version}
        with pytest.raises(ValidationError, match="schema_version"):
            Report.model_validate(invalid)
    assert report["criteria"]["AC-1-1"]["rate"] == 100
    assert (reports_dir / "report.html").read_text(encoding="utf-8")
    assert "AC-1-1" in result.output
    assert "TOTAL" in result.output
    assert _compact(str(reports_dir / "report.html")) in _compact(result.output)


def test_rerun_overwrites_the_report(tmp_path: Path) -> None:
    results_file = _write_experiment(tmp_path)
    runner.invoke(app, ["report", "--results-file", str(results_file)])
    _results(success=False).save(results_file)

    result = runner.invoke(app, ["report", "--results-file", str(results_file)])

    assert result.exit_code == 0, result.output
    report = json.loads((results_file.parent / "report.json").read_text())
    assert report["criteria"]["AC-1-1"]["rate"] == 0


def test_relative_results_path_resolves_against_the_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    results_file = _write_experiment(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["report", "--results-file", str(results_file.relative_to(tmp_path))]
    )

    assert result.exit_code == 0, result.output
    assert (results_file.parent / "report.json").exists()


def test_missing_specification_is_not_an_error(tmp_path: Path) -> None:
    results_file = _write_experiment(tmp_path, with_specification=False)

    result = runner.invoke(app, ["report", "--results-file", str(results_file)])

    assert result.exit_code == 0, result.output
    assert "TOTAL" in result.output
    assert "notwritten" in _compact(result.output)
    expected = results_file.parent.parent.parent / "inputs" / "specification.yaml"
    assert _compact(str(expected)) in _compact(result.output)
    assert not (results_file.parent / "report.json").exists()


def test_report_requires_results_inside_execution_outputs(tmp_path: Path) -> None:
    original = _write_experiment(tmp_path)
    moved = tmp_path / "elsewhere" / "results.json"
    moved.parent.mkdir()
    shutil.copy(original, moved)

    result = runner.invoke(app, ["report", "--results-file", str(moved)])

    assert result.exit_code == 1, result.output
    assert "outputs/reports/" in result.output
    assert not (tmp_path / "outputs" / "reports" / "report.json").exists()


def test_missing_results_file_exits_one(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["report", "--results-file", str(tmp_path / "absent.json")]
    )

    assert result.exit_code == 1
    assert "cannotreadresultsfile" in _compact(result.output)


def test_malformed_results_file_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text("{", encoding="utf-8")

    result = runner.invoke(app, ["report", "--results-file", str(path)])

    assert result.exit_code == 1
    assert "cannotreadresultsfile" in _compact(result.output)


def test_wrong_schema_version_exits_one_with_the_reason(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text('{"schema_version": 99, "run_id": "r"}', encoding="utf-8")

    result = runner.invoke(app, ["report", "--results-file", str(path)])

    assert result.exit_code == 1
    assert "Unsupportedschema_version99(expected2)" in _compact(result.output)


def test_root_cli_exposes_insights_report() -> None:
    from metis_cli import app as root_app

    result = runner.invoke(root_app, ["insights", "report", "--help"])

    assert result.exit_code == 0, result.output
    assert "--results-file" in result.output


def test_new_grader_record_format_is_rejected_with_a_clear_message(
    tmp_path: Path,
) -> None:
    """Grader redesign (#428): insights cannot read GraderRecord files until #454."""
    results_file = tmp_path / "reports" / "results.json"
    results_file.parent.mkdir(parents=True)
    results_file.write_text(
        '{"schema_version": 2, "run_id": "r", "records": []}', encoding="utf-8"
    )

    result = runner.invoke(app, ["report", "--results-file", str(results_file)])

    assert result.exit_code == 1
    assert "GraderRecord" in result.output
