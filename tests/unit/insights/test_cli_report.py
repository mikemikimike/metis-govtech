"""Tests for the ``metis insights report`` command."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from metis.insights._legacy_results import (
    EvaluationResults,
    TurnGraderResult,
    TurnReport,
)
from metis.insights._models import Report
from metis.insights.cli import app

runner = CliRunner()

SPECIFICATION = 'schema_version: 1\nid: test-exp\nrunner_factory_ref: tests.unit.engine.test_runner_ref.StubRunnerFactory\npersonas:\n- id: alice\n  description: test persona\n  name: alice\nscenarios:\n- id: task-1\n  description: test scenario\n  name: task-1\ntarget:\n  name: Test target\n  users: Test users\n  description: Test target\ntasks:\n- id: TC-001\n  scenario_ref: task-1\n  persona_ref: alice\n  fixtures: []\n  num_trials: 1\n  behaviour_refs:\n  - EB-1\nfeatures:\n- id: F-1\n  name: Responses\n  description: Responses\n  behaviours:\n  - id: EB-1\n    name: Respond\n    description: Respond correctly\n    measured: true\n    criteria:\n    - id: AC-1-1\n      name: Check 1\n      description: "Given a request, when the agent responds, then the requirement is met."\n      grader_fqn: metis.library.graders.TurnBudgetGrader\n      grader_args: {}\n'


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
    assert report["schema_version"] == 1
    assert Report.model_validate(report).target == "Test target"
    without_version = {
        key: value for key, value in report.items() if key != "schema_version"
    }
    assert Report.model_validate(without_version).schema_version == 1
    for unsupported_version in (2, None):
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
    assert "Unsupportedschema_version99(expected1)" in _compact(result.output)


def test_root_cli_exposes_insights_report() -> None:
    from metis_cli import app as root_app

    result = runner.invoke(root_app, ["insights", "report", "--help"])

    assert result.exit_code == 0, result.output
    assert "--results-file" in result.output


@pytest.mark.parametrize(
    "outcomes", [["passed", "failed", "skipped", "errored"], ["errored"]]
)
def test_recorded_results_keep_outcomes_and_run_settings(
    tmp_path: Path, outcomes: list[str]
) -> None:
    import yaml

    from metis.insights._aggregation import aggregate_graders
    from metis.insights._results import load_results

    results_file = _write_experiment(tmp_path)
    spec_path = results_file.parents[2] / "inputs" / "specification.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    criteria = spec["features"][0]["behaviours"][0]["criteria"]
    criteria.append({**criteria[0], "id": "AC-1-2"})
    spec_path.write_text(yaml.safe_dump(spec))
    records = [
        {
            "session_id": "session-1",
            "scenario_id": "task-1",
            "task_id": "TC-001",
            "trial_index": trial,
            "criterion_id": cid,
            "grader_fqn": "metis.library.graders.TurnBudgetGrader",
            "grader_args": {"max_turns": trial + 4},
            "results": [
                {
                    "outcome": outcome,
                    "score": 1.0
                    if outcome == "passed"
                    else 0.0
                    if outcome == "failed"
                    else None,
                    "reason": outcome,
                }
                for outcome in outcomes
            ],
        }
        for trial, cid in [(1, "AC-1-1"), (2, "AC-1-1"), (1, "AC-1-2")]
    ]
    results_file.write_text(json.dumps({"run_id": "records", "records": records}))

    result = runner.invoke(app, ["report", "--results-file", str(results_file)])

    assert result.exit_code == 0, result.output
    report = json.loads((results_file.parent / "report.json").read_text())
    assert report["sessions"] == 1
    assert report["turns"] == 0
    assert report["results"] == 3 * len(outcomes)
    criterion = report["criteria"]["AC-1-1"]
    assert criterion["error"] == 2
    assert criterion["rate"] == (50 if "passed" in outcomes else None)
    assert len(criterion["evidence"]) == 2 * len(outcomes)
    assert report["criteria"]["AC-1-2"]["error"] == 1
    for evidence, record in zip(
        criterion["evidence"], [r for r in records[:2] for _ in outcomes], strict=True
    ):
        assert evidence["grader_args"] == record["grader_args"]
        assert evidence["grader_fqn"] == record["grader_fqn"]
        assert evidence["trial_index"] == record["trial_index"]
        assert evidence["task_id"] == "TC-001"
        assert evidence["scenario"] == "task-1"
        assert evidence["session"] == "session-1"
        assert evidence["trace"] == evidence["turn"] == ""
    assert {e["status"] for e in criterion["evidence"]} == (
        {"pass", "fail", "skip", "error"} if len(outcomes) == 4 else {"error"}
    )
    loaded = load_results(results_file)
    aggregate = aggregate_graders([], [s.model_dump() for s in loaded.session_results])
    assert aggregate["AC-1-1"]["error"] == 2
    assert aggregate["AC-1-1"]["scores"] == (
        [1.0, 0.0, 1.0, 0.0] if len(outcomes) == 4 else []
    )
    assert "Error" in result.output
    page = (results_file.parent / "report.html").read_text()
    assert "Recorded grader settings" in page
    assert "Grader error" in page


def test_report_keeps_trial_results_separate_for_one_session(tmp_path: Path) -> None:
    import yaml

    from metis.insights._report import build_report
    from metis.insights._results import load_results

    results_file = _write_experiment(tmp_path)
    records = [
        {
            "session_id": "shared-session",
            "scenario_id": "task-1",
            "task_id": "TC-001",
            "trial_index": trial,
            "criterion_id": "AC-1-1",
            "grader_fqn": "metis.library.graders.TurnBudgetGrader",
            "grader_args": {"max_turns": 5},
            "results": [{"outcome": outcome, "score": score, "reason": outcome}],
        }
        for trial, outcome, score in [(1, "passed", 1.0), (2, "errored", None)]
    ]
    results_file.write_text(json.dumps({"run_id": "records", "records": records}))
    loaded = load_results(results_file)
    trials = [
        {
            "id": f"TC-001-{trial}",
            "task_id": "TC-001",
            "trial_index": trial,
            "session": "shared-session",
            "scenario": "task-1",
            "persona": "alice",
            "stopReason": "goal_achieved",
            "message": "done",
            "failureSource": "outcome",
            "turns": 1,
        }
        for trial in (1, 2)
    ]
    report = Report.model_validate(
        build_report(
            yaml.safe_load(SPECIFICATION),
            [],
            session_graders=[s.model_dump() for s in loaded.session_results],
            trial_outcomes=trials,
        )
    )
    first, second = report.resultTable.rows
    assert first.results["AC-1-1"].rate == 100
    assert first.results["AC-1-1"].error == 0
    assert second.results["AC-1-1"].rate is None
    assert second.results["AC-1-1"].error == 1
    assert second.results["AC-1-1"].fail == 0


def test_unmatched_records_show_identity_settings_and_errors(tmp_path: Path) -> None:
    import subprocess

    from metis.insights._report_page import REPORT_SCRIPT

    results_file = _write_experiment(tmp_path)
    results_file.write_text(
        json.dumps(
            {
                "run_id": "unmatched",
                "records": [
                    {
                        "session_id": "session-unknown",
                        "scenario_id": "scenario-unknown",
                        "task_id": "task-unknown",
                        "trial_index": 3,
                        "criterion_id": "criterion-unknown",
                        "grader_fqn": "example.CountGrader",
                        "grader_args": {"expected_count": 17},
                        "results": [
                            {
                                "outcome": "errored",
                                "score": None,
                                "reason": "service unavailable",
                            },
                            {
                                "outcome": "failed",
                                "score": 0.0,
                                "reason": "count was 10",
                            },
                        ],
                    }
                ],
            }
        )
    )
    result = runner.invoke(app, ["report", "--results-file", str(results_file)])
    assert result.exit_code == 0, result.output
    report = json.loads((results_file.parent / "report.json").read_text())
    group = report["unmapped"][0]
    assert group["error"] == group["fail"] == 1
    assert report["scores"]["graderPassRate"]["rate"] is None
    assert [item["status"] for item in group["evidence"]] == ["error", "fail"]

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute report rendering")
    constants = REPORT_SCRIPT[
        REPORT_SCRIPT.index("const LABELS=") : REPORT_SCRIPT.index("const clip=")
    ]
    renderers = REPORT_SCRIPT[
        REPORT_SCRIPT.index("const resultCounts=") : REPORT_SCRIPT.index(
            "const unmappedPanel="
        )
    ]
    script = (
        constants
        + renderers
        + "\nprocess.stdout.write(unmappedResults("
        + json.dumps(report["unmapped"])
        + "));"
    )
    rendered = subprocess.run(
        [node, "-e", script], check=True, capture_output=True, text=True
    ).stdout
    for text in [
        "criterion-unknown",
        "task-unknown",
        "Trial 3",
        "session-unknown",
        "scenario-unknown",
        "example.CountGrader",
        "expected_count",
        "17",
        "Grader error",
        "Fail",
        "service unavailable",
        "count was 10",
    ]:
        assert text in rendered
