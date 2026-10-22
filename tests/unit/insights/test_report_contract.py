"""The report.json, report.html, and terminal contract of `metis insights report`."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from typer.testing import CliRunner

from metis.core.reporting import EvaluationResults, GraderRecord
from metis.insights._aggregation import summarize_run
from metis.insights._models import Report
from metis.insights._report import build_report, load_report_sources
from metis.insights._report_page import REPORT_SCRIPT, render_report_page
from metis.insights.cli import app
from metis.insights.report import format_terminal_summary
from tests.fixtures.insights.report_experiment import (
    grader_record,
    grader_records,
    write_experiment,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def experiment(tmp_path: Path) -> Path:
    return write_experiment(tmp_path / "experiment", grader_records())


def _build(
    experiment: Path, records: list[GraderRecord] | None = None
) -> dict[str, Any]:
    sources = load_report_sources(experiment.parents[2])
    assert sources is not None
    specification, trials = sources
    results = EvaluationResults(
        run_id="run-1", records=grader_records() if records is None else records
    )
    data = build_report(specification, results, trial_outcomes=trials)
    return Report.model_validate(data).model_dump(by_alias=True)


def _counts(item: dict[str, Any]) -> tuple[int, int, int, int]:
    return item["pass"], item["fail"], item["skip"], item["error"]


def test_run_verdict_uses_equal_weight_mean_and_recorded_threshold() -> None:
    record = grader_record("T-1", 1, "C-1", 0.9, 0.1, 0.8, "errored", threshold=0.6)
    summary = summarize_run(record)
    assert (summary.score, summary.threshold, summary.outcome) == (
        pytest.approx(0.6),
        0.6,
        "passed",
    )
    record.grader_args["threshold"] = 0.61
    assert summarize_run(record).outcome == "failed"


@pytest.mark.parametrize(
    "threshold", [None, True, "0.5", -0.1, 1.1, float("nan"), float("inf")]
)
def test_scored_run_requires_valid_recorded_threshold(threshold: object) -> None:
    with pytest.raises(ValueError, match="Invalid recorded threshold.*C-1"):
        summarize_run(grader_record("T-1", 1, "C-1", 0.9, threshold=threshold))


@pytest.mark.parametrize(
    "outcomes, expected",
    [(["skipped"], "skipped"), (["skipped", "errored"], "errored")],
)
def test_unscored_run_verdict(outcomes: list[str], expected: str) -> None:
    summary = summarize_run(grader_record("T-1", 1, "C-1", *outcomes, threshold=None))
    assert (summary.outcome, summary.score) == (expected, None)


def test_criterion_pools_its_runs(experiment: Path) -> None:
    criteria = _build(experiment)["criteria"]
    assert _counts(criteria["C-1"]) == (4, 0, 0, 0)
    assert criteria["C-1"]["rate"] == 100
    assert criteria["C-1"]["mean_score"] == pytest.approx((0.9 + 0.6 + 0.9 + 0.7) / 4)
    assert (criteria["C-2"]["rate"], criteria["C-2"]["mean_score"]) == (
        0,
        pytest.approx(0.2),
    )


def test_levels_above_criterion_average_their_evaluated_children(
    experiment: Path,
) -> None:
    report = _build(experiment)
    behaviour = report["behaviours"]["B-1"]
    # C-1 has four passed runs and C-2 one failed run. Each criterion counts once.
    assert behaviour["rate"] == 50
    assert behaviour["mean_score"] == pytest.approx((0.775 + 0.2) / 2)
    assert _counts(behaviour) == (4, 1, 0, 0)
    # B-2 has no evaluated criterion, so the feature uses B-1 only.
    feature = report["features"][0]
    assert (feature["rate"], feature["mean_score"]) == (50, behaviour["mean_score"])
    assert _counts(feature) == (4, 1, 1, 1)
    overall = report["scores"]["graderPassRate"]
    assert (overall["rate"], overall["mean_score"]) == (50, feature["mean_score"])
    assert (overall["ran"], overall["skip"], overall["error"]) == (5, 1, 1)


def test_level_without_evaluated_children_has_no_rate(experiment: Path) -> None:
    report = _build(experiment)
    behaviour = report["behaviours"]["B-2"]
    assert (behaviour["rate"], behaviour["mean_score"], behaviour["status"]) == (
        None,
        None,
        "error",
    )
    assert report["criteria"]["C-3"]["blank"]["cause"] == "grader error"


def test_table_row_pools_the_trials_of_one_test_case(experiment: Path) -> None:
    records = [*grader_records(), grader_record("T-1", 2, "C-2", 0.9)]
    rows = {
        row["task_id"]: row
        for row in _build(experiment, records)["resultTable"]["rows"]
    }
    assert set(rows) == {"T-1", "T-2"}
    cell = rows["T-1"]["results"]["C-2"]
    assert (cell["pass"], cell["fail"], cell["evaluated"], cell["rate"]) == (
        1,
        1,
        2,
        50,
    )
    assert cell["mean_score"] == pytest.approx(0.55)
    by_trial = {trial["trial_index"]: trial for trial in rows["T-1"]["trials"]}
    assert by_trial[1]["results"]["C-2"]["rate"] == 0
    assert by_trial[2]["results"]["C-2"]["rate"] == 100
    assert by_trial[1]["session"] == "T-1-1"


def test_trial_data_carries_engine_turn_count(experiment: Path) -> None:
    report = _build(experiment)
    assert {trial["total_turns"] for trial in report["trials"]["items"]} == {3}
    assert report["scores"]["trialSuccess"]["successful"] == 4


def test_criterion_shows_recorded_judge_models(experiment: Path) -> None:
    records = [*grader_records(), grader_record("T-2", 2, "C-2", 0.9, model="judge-b")]
    criteria = _build(experiment, records)["criteria"]
    assert criteria["C-1"]["judge_models"] == ["judge-a"]
    assert criteria["C-2"]["judge_models"] == ["judge-a", "judge-b"]


def test_criterion_keeps_its_plain_description(experiment: Path) -> None:
    criterion = _build(experiment)["criteria"]["C-1"]
    assert criterion["description"] == "The response meets check C-1."


def test_grader_error_is_separate_from_failure(experiment: Path) -> None:
    criterion = _build(experiment)["criteria"]["C-3"]
    assert {item["status"] for item in criterion["evidence"]} == {"skip", "error"}
    assert (criterion["fail"], criterion["error"], criterion["rate"]) == (0, 1, None)


def test_evidence_keeps_recorded_facts_and_settings(experiment: Path) -> None:
    records = grader_records()
    records[0].grader_args["threshold"] = 0.4
    evidence = _build(experiment, records)["criteria"]["C-1"]["evidence"]
    first, second = evidence[0], evidence[1]
    assert (first["result_number"], second["result_number"]) == (1, 2)
    assert (first["task_id"], first["trial_index"], first["session"]) == (
        "T-1",
        1,
        "T-1-1",
    )
    assert first["grader_fqn"] == "g.one.Grader"
    assert first["grader_args"] == {"threshold": 0.4, "model": "judge-a"}
    assert evidence[2]["grader_args"]["threshold"] == 0.5
    assert (first["run_score"], first["run_threshold"], first["run_outcome"]) == (
        pytest.approx(0.9),
        0.4,
        "passed",
    )


def test_partial_error_stays_in_raw_evidence(experiment: Path) -> None:
    records = [grader_record("T-1", 1, "C-1", 0.7, 0.8, "errored", "skipped")]
    report = _build(experiment, records)
    criterion = report["criteria"]["C-1"]
    assert _counts(criterion) == (1, 0, 0, 0)
    assert [item["outcome"] for item in criterion["evidence"]] == [
        "passed",
        "passed",
        "errored",
        "skipped",
    ]
    assert report["results"] == 4


def test_unmatched_records_stay_in_unmapped_with_each_reason(experiment: Path) -> None:
    records = grader_records()
    records[0].scenario_id = "S-other"
    records[1].session_id = "missing-session"
    report = _build(experiment, records)
    groups = [group for group in report["unmapped"] if group["criterion_id"] == "C-1"]
    assert {group["why"] for group in groups} == {
        "The result scenario differs from the task scenario.",
        "No saved trial matches the task, trial index, and session.",
    }
    originals = [group["records"][0] for group in groups]
    assert records[0].model_dump() in originals
    assert records[1].model_dump() in originals
    assert _counts(report["criteria"]["C-1"]) == (2, 0, 0, 0)
    assert report["results"] == sum(len(record.results) for record in records)


def test_duplicate_record_for_one_criterion_is_rejected(experiment: Path) -> None:
    records = [*grader_records(), grader_records()[0]]
    with pytest.raises(ValueError, match="Duplicate grader record"):
        _build(experiment, records)


def test_grader_names_keep_full_grader_identity(experiment: Path) -> None:
    report = _build(experiment)
    column = report["resultTable"]["features"][0]["columns"][0]
    assert (column["criterion"], column["grader_name"], column["grader_fqn"]) == (
        "C-1",
        "Grader",
        "g.one.Grader",
    )
    assert report["criteria"]["C-2"]["grader_fqn"] == "g.two.Grader"
    summary = format_terminal_summary(
        EvaluationResults(run_id="run-1", records=grader_records())
    )
    assert "C-1 / g.one.Grader" in summary
    assert "C-2 / g.two.Grader" in summary


def test_terminal_last_row_is_mean_of_criteria() -> None:
    summary = format_terminal_summary(
        EvaluationResults(run_id="run-1", records=grader_records())
    )
    last = summary.splitlines()[-1].split()
    assert last[:3] == ["MEAN", "OF", "CRITERIA"]
    assert last[3:7] == ["4", "1", "1", "1"]
    assert last[7] == "50.0%"


def test_empty_run_has_unavailable_rates(experiment: Path) -> None:
    report = _build(experiment, [])
    assert report["results"] == 0
    assert report["scores"]["graderPassRate"]["rate"] is None
    assert all(criterion["rate"] is None for criterion in report["criteria"].values())


def test_report_version_is_one(experiment: Path) -> None:
    report = _build(experiment)
    assert report["schema_version"] == 1
    with pytest.raises(ValueError, match="schema_version"):
        Report.model_validate({**report, "schema_version": 2})


def test_html_shows_settings_errors_and_unmatched_results(experiment: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to run the report renderer")
    records = grader_records()
    records[6].scenario_id = "S-other"
    report = _build(experiment, records)
    renderers = (
        REPORT_SCRIPT[
            REPORT_SCRIPT.index("const LABELS=") : REPORT_SCRIPT.index("const clip=")
        ]
        + REPORT_SCRIPT[
            REPORT_SCRIPT.index("const resultCounts=") : REPORT_SCRIPT.index(
                "function filterOptions"
            )
        ]
        + REPORT_SCRIPT[
            REPORT_SCRIPT.index("function evidenceList") : REPORT_SCRIPT.index(
                "function individualResults"
            )
        ]
    )
    script = f"{renderers}\nprocess.stdout.write(unmappedResults({json.dumps(report['unmapped'])}));"
    rendered = subprocess.run(
        [node, "-e", script], check=True, capture_output=True, text=True
    ).stdout
    for text in (
        "Results without a matching criterion",
        "C-3 / g.three.Grader",
        "The result scenario differs from the task scenario.",
        "Grader error",
        "Recorded grader settings",
        "judge-a",
        "T-2 trial 1",
    ):
        assert text in rendered


def test_html_escapes_embedded_text(experiment: Path) -> None:
    records = grader_records()
    records[0].results[0].reason = "</script><script>alert(1)</script>"
    html = render_report_page(_build(experiment, records), title="<Target>")
    assert "<title>&lt;Target&gt;</title>" in html
    assert "</script><script>alert(1)</script>" not in html
    assert "<\\/script>" in html


def test_cli_writes_both_valid_reports(experiment: Path) -> None:
    result = CliRunner().invoke(app, ["report", "--results-file", str(experiment)])
    assert result.exit_code == 0, result.output
    data = Report.model_validate_json((experiment.parent / "report.json").read_text())
    assert data.results == 8
    assert (experiment.parent / "report.html").read_text().startswith("<!DOCTYPE html>")


def test_cli_reports_invalid_threshold(tmp_path: Path) -> None:
    records = grader_records()
    records[0].grader_args = {}
    path = write_experiment(tmp_path / "experiment", records)
    result = CliRunner().invoke(app, ["report", "--results-file", str(path)])
    assert result.exit_code == 1
    assert "Invalid recorded threshold" in result.output
    assert "C-1" in result.output


def test_cli_rejects_results_without_grader_records(experiment: Path) -> None:
    experiment.write_text(json.dumps({"run_id": "run-1", "turn_results": []}))
    result = CliRunner().invoke(app, ["report", "--results-file", str(experiment)])
    assert result.exit_code == 1
    assert "turn_results" in result.output
    assert not (experiment.parent / "report.json").exists()
