"""Tests for the ``metis engine evaluate`` command."""

from __future__ import annotations

import shlex
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase, Turn
from typer.testing import CliRunner

from metis.core.reporting import EvaluationResults
from metis.engine import cli
from metis.engine.cli import EvaluationOutcome, app
from metis.engine.evaluation.types import (
    EvalResult,
    GraderResult,
    SessionResult,
    TurnResult,
)
from metis.engine.simulation.types import (
    GraderRef,
    TrialConfig,
    TrialOutcome,
    TrialRecord,
)

runner = CliRunner()

MINIMAL_EXPERIMENT = "schema_version: 2\nid: test-exp\nrunner_factory_ref: tests.unit.engine.test_runner_ref.StubRunnerFactory\npersonas:\n- id: alice\n  description: test persona\n  name: alice\nscenarios:\n- id: task-1\n  description: test scenario\n  name: task-1\nproduct:\n  name: Test product\n  users: Test users\n  description: Test product\ntasks:\n- id: TC-001\n  scenario_ref: task-1\n  persona_ref: alice\n  fixtures: []\n  num_trials: 1\n  criterion_refs:\n  - AC-1-1\nfeatures:\n- id: F-1\n  name: Responses\n  description: Responses\n  behaviours:\n  - id: EB-1\n    name: Respond\n    description: Respond correctly\n    measured: true\n    criteria:\n    - id: AC-1-1\n      name: Check 1\n      description:\n        given: a request\n        when: the agent responds\n        then: the requirement is met\n      grader_fqn: metis.library.graders.TurnBudgetGrader\n      grader_args: {}\n"


def _write_snapshot(experiment_dir: Path, content: str = MINIMAL_EXPERIMENT) -> Path:
    inputs_dir = experiment_dir / "inputs"
    inputs_dir.mkdir(parents=True)
    (inputs_dir / "specification.yaml").write_text(content)
    return experiment_dir


def _write_record(
    experiment_dir: Path,
    *,
    run_name: str = "task-1-alice-1",
    session_id: str = "session-1",
) -> Path:
    record = TrialRecord(
        config=TrialConfig(
            persona="alice",
            scenario="task-1",
            grader_refs=[GraderRef(fqn="example.graders.TestGrader", args={})],
        ),
        outcome=TrialOutcome(
            stop_reason="goal_achieved",
            total_turns=1,
            duration_seconds=1.0,
        ),
        target_session_id=session_id,
    )
    record_path = experiment_dir / "trials" / run_name / "record.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(record.model_dump_json())
    return record_path


def _grader_eval_result() -> EvalResult:
    turn_graders = [
        GraderResult(
            name="Routing Accuracy",
            score=0.9,
            reason="Correct route",
            success=True,
            skipped=False,
            evaluation_cost=0.012,
            input_tokens=120,
            output_tokens=30,
        ),
        GraderResult(
            name="Turn Budget",
            score=1.0,
            reason="Within budget",
            success=True,
            skipped=False,
        ),
    ]
    session_grader = GraderResult(
        name="Session Efficiency",
        score=0.7,
        reason="Efficient session",
        success=True,
        skipped=False,
    )
    return EvalResult(
        turn_results=[
            TurnResult(
                llm_test_case=LLMTestCase(
                    input="hi", actual_output="ok", name="trace-1"
                ),
                grader_results=turn_graders,
            )
        ],
        session_results=[
            SessionResult(
                conversational_test_case=ConversationalTestCase(
                    turns=[Turn(role="user", content="hi")], name="session-1"
                ),
                grader_results=[session_grader],
            )
        ],
    )


def _write_experiment_dir(
    root: Path,
    *,
    name: str = "test-exp-20260101-010101",
    content: str = MINIMAL_EXPERIMENT,
) -> Path:
    """Write a simulation output directory with its frozen input snapshot."""
    experiment_dir = root / "experiments" / name
    experiment_dir.mkdir(parents=True)
    _write_snapshot(experiment_dir, content)
    return experiment_dir


def _compact(value: str) -> str:
    return "".join(value.split())


def test_evaluate_scores_the_named_experiment_directory(
    monkeypatch, tmp_path: Path
) -> None:
    target = _write_experiment_dir(tmp_path, name="test-exp-20260101-010101")
    # A second output exists for the same experiment id. The command must use the
    # path it is given, and must not choose one by timestamp.
    _write_experiment_dir(tmp_path, name="test-exp-20260102-010101")

    calls: list[Path] = []

    def fake_evaluation(
        path: Path,
        *,
        langfuse_timeout: int,
        verbose: int,
        quiet: bool,
    ) -> EvaluationOutcome:
        calls.append(path)
        assert langfuse_timeout == 120
        assert verbose == 1
        assert not quiet
        return EvaluationOutcome(1, 1, 0, None)

    monkeypatch.setattr(cli, "_run_evaluation", fake_evaluation)
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--experiment-dir",
            str(target),
            "--langfuse-timeout",
            "120",
            "-v",
        ],
    )

    assert result.exit_code == 0
    assert calls == [target.resolve()]
    assert f"Selectedexperiment:{_compact(str(target.resolve()))}" in _compact(
        result.output
    )


def test_evaluate_rejects_a_path_that_does_not_exist(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["evaluate", "--experiment-dir", str(tmp_path / "missing")]
    )

    assert result.exit_code == 1
    assert "doesnotexist" in _compact(result.output)


def test_evaluate_rejects_a_path_that_is_not_a_directory(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "record.json"
    not_a_directory.write_text("{}")

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(not_a_directory)])

    assert result.exit_code == 1
    assert "doesnotexist" in _compact(result.output)


def test_evaluate_rejects_a_directory_without_an_input_snapshot(tmp_path: Path) -> None:
    unrelated_dir = tmp_path / "not-an-experiment"
    unrelated_dir.mkdir()

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(unrelated_dir)])

    assert result.exit_code == 1
    assert "isnotasimulationoutputdirectory" in _compact(result.output)
    assert "metisenginesimulate" in _compact(result.output)


def test_evaluate_fails_when_the_input_snapshot_has_no_specification_file(
    tmp_path: Path,
) -> None:
    experiment_dir = tmp_path / "experiments" / "test-exp-20260101-010101"
    (experiment_dir / "inputs").mkdir(parents=True)

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(experiment_dir)])

    assert result.exit_code != 0
    assert _compact(str(experiment_dir.resolve())) in _compact(result.output)
    assert "specification.yaml" in result.output


def test_evaluate_fails_for_a_malformed_trial_record(tmp_path: Path) -> None:
    experiment_dir = _write_experiment_dir(tmp_path)
    malformed_record = experiment_dir / "trials" / "run-1" / "record.json"
    malformed_record.parent.mkdir(parents=True)
    malformed_record.write_text("{}")

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(experiment_dir)])

    assert result.exit_code != 0
    assert "trial record" in result.output
    assert (
        "EVALUATION FAILED — failed to load trial record"
        in (experiment_dir / "logs" / "evaluate.log").read_text()
    )


def test_evaluate_with_no_run_records_is_a_noop(tmp_path: Path) -> None:
    experiment_dir = _write_experiment_dir(tmp_path)

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(experiment_dir)])

    assert result.exit_code == 0
    assert "nothing to evaluate" in result.output
    assert (
        "EVALUATION COMPLETED — 0 records"
        in (experiment_dir / "logs" / "evaluate.log").read_text()
    )


def _patch_evaluation(monkeypatch, *, test_cases: list[object]) -> None:
    monkeypatch.setattr("metis.engine.extractor.get_langfuse_client", lambda: object())
    monkeypatch.setattr(
        "metis.engine.extractor.fetch_by_session_id",
        lambda *_args, **_kwargs: SimpleNamespace(test_cases=test_cases),
    )
    monkeypatch.setattr(
        "metis.engine.evaluation.evaluate",
        lambda *_args, **_kwargs: _grader_eval_result(),
    )


def test_evaluation_writes_results_file_and_prints_report_command(
    monkeypatch, tmp_path: Path
) -> None:
    output = _write_experiment_dir(tmp_path)
    _write_record(output)
    _patch_evaluation(monkeypatch, test_cases=[object()])

    first = runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])
    second = runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    results_file = output.resolve() / "reports" / "results.json"
    results = EvaluationResults.load_file(results_file)
    assert results.run_id == "report"
    assert len(results.turn_results) == 1
    assert len(results.session_results) == 1
    # Engine no longer builds the report; insights does.
    assert not (output / "reports" / "report.json").exists()
    assert not (output / "reports" / "report.html").exists()
    command = shlex.join(
        ["metis", "insights", "report", "--results-file", str(results_file)]
    )
    assert _compact(f"Report: {command}") in _compact(second.output)
    evaluation_log = (output / "logs" / "evaluate.log").read_text()
    assert evaluation_log.count("EVALUATION STARTED") == 1
    assert "RESULTS WRITTEN" in evaluation_log


def test_report_command_is_shell_quoted_for_paths_with_spaces(
    monkeypatch, tmp_path: Path
) -> None:
    output = _write_experiment_dir(tmp_path, name="test exp 20260101-010101")
    _write_record(output)
    _patch_evaluation(monkeypatch, test_cases=[object()])

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])

    assert result.exit_code == 0
    results_file = output.resolve() / "reports" / "results.json"
    quoted = shlex.join(["--results-file", str(results_file)])
    assert "'" in quoted
    assert _compact(quoted) in _compact(result.output)


def test_evaluation_with_no_successful_records_writes_no_results(
    monkeypatch, tmp_path: Path
) -> None:
    output = _write_experiment_dir(tmp_path)
    _write_record(output)
    _patch_evaluation(monkeypatch, test_cases=[])

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])

    assert result.exit_code == 0
    assert "No evaluable test cases" in result.output
    assert not (output / "reports" / "results.json").exists()
    assert "metisinsightsreport" not in _compact(result.output)


def test_reevaluation_with_no_successes_removes_stale_results(
    monkeypatch, tmp_path: Path
) -> None:
    output = _write_experiment_dir(tmp_path)
    _write_record(output)
    _patch_evaluation(monkeypatch, test_cases=[object()])
    runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])
    assert (output / "reports" / "results.json").exists()
    _patch_evaluation(monkeypatch, test_cases=[])

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])

    assert result.exit_code == 0
    # A results file from an earlier evaluation must not outlive one that scored
    # nothing, or `metis insights report` would re-stamp stale scores as current.
    assert not (output / "reports" / "results.json").exists()


def test_report_command_keeps_square_brackets_in_paths(
    monkeypatch, tmp_path: Path
) -> None:
    output = _write_experiment_dir(tmp_path, name="test [draft] 20260101-010101")
    _write_record(output)
    _patch_evaluation(monkeypatch, test_cases=[object()])

    result = runner.invoke(app, ["evaluate", "--experiment-dir", str(output)])

    assert result.exit_code == 0
    results_file = output.resolve() / "reports" / "results.json"
    command = shlex.join(
        ["metis", "insights", "report", "--results-file", str(results_file)]
    )
    assert _compact(f"Report: {command}") in _compact(result.output)


def test_evaluation_progress_advances_for_success_and_soft_failure(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    output = _write_snapshot(tmp_path / "experiment")
    _write_record(output, run_name="run-1", session_id="session-1")
    _write_record(output, run_name="run-2", session_id="session-2")

    events: list[tuple[str, Any]] = []

    class FakeProgress:
        def __enter__(self):
            events.append(("enter", None))
            return self

        def __exit__(self, *_args: object) -> None:
            events.append(("exit", None))

        def add_task(self, description: str, *, total: int) -> int:
            events.append(("add", (description, total)))
            return 1

        def update(self, _task_id: int, **kwargs: object) -> None:
            events.append(("update", kwargs))

    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(cli, "_create_evaluation_progress", FakeProgress)
    monkeypatch.setattr("metis.engine.extractor.get_langfuse_client", lambda: object())

    def fetch(session_id: str, *_args: object, **_kwargs: object) -> object:
        if session_id == "session-2":
            raise RuntimeError("trace unavailable")
        return SimpleNamespace(test_cases=[object()])

    monkeypatch.setattr(
        "metis.engine.extractor.fetch_by_session_id",
        fetch,
    )
    monkeypatch.setattr(
        "metis.engine.evaluation.evaluate",
        lambda *_args, **_kwargs: _grader_eval_result(),
    )

    outcome = cli._run_evaluation(
        output,
        langfuse_timeout=90,
        verbose=0,
        quiet=False,
    )

    updates = [payload for event, payload in events if event == "update"]
    descriptions = [
        update["description"] for update in updates if "description" in update
    ]
    advances = [update.get("advance", 0) for update in updates]

    assert outcome.successful_records == 1
    assert outcome.failed_records == 1
    assert "alice x task-1 — extracting" in descriptions
    assert "alice x task-1 — evaluating" in descriptions
    assert "alice x task-1 — failed" in descriptions
    assert sum(advances) == 2
    assert events[0][0] == "enter"
    assert events[-1][0] == "exit"
    assert "WARNING: Evaluation failed: trace unavailable" in capsys.readouterr().out
    evaluation_log = (output / "logs" / "evaluate.log").read_text()
    assert "alice x task-1 — EXTRACTING" in evaluation_log
    assert "alice x task-1 — EVALUATING" in evaluation_log
    assert "alice x task-1 — DONE" in evaluation_log
    assert "alice x task-1 — FAILED — trace unavailable" in evaluation_log
    assert '"fqn": "example.graders.TestGrader"' in evaluation_log
    assert '"grader": "Routing Accuracy"' in evaluation_log
    assert '"score": 0.9' in evaluation_log
    assert '"success": true' in evaluation_log
    assert '"reason": "Correct route"' in evaluation_log
    assert '"evaluation_cost": 0.012' in evaluation_log
    assert '"input_tokens": 120' in evaluation_log
    assert '"output_tokens": 30' in evaluation_log
    assert '"scope": "session"' in evaluation_log
    assert '"grader": "Session Efficiency"' in evaluation_log
    assert '"grader": "Turn Budget"' in evaluation_log
    assert '"skipped": false' in evaluation_log

    cli._update_evaluation_progress(
        None,
        None,
        record_number=1,
        total_records=2,
        label="alice x task-1",
        phase="extracting",
    )
    assert "Evaluation 1/2: alice x task-1 — extracting" in capsys.readouterr().out
