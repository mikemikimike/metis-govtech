"""A trial's conversation, read from the traces `evaluate` saved, in the report (#462, #503)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from metis.core import SessionTraces, execution_layout
from metis.core.reporting import EvaluationResults
from metis.core.trace_processing import Problem, turns
from metis.core.traces import Observation, Trace
from metis.insights._conversation import conversation_rows, read_turns, turn_count_note
from metis.insights._models import Report
from metis.insights._report import build_report, load_report_sources
from metis.insights._report_page import REPORT_SCRIPT, render_report_page
from tests.fixtures.insights.report_experiment import (
    grader_records,
    save_trial_traces,
    trial_record,
    write_experiment,
)
from tests.fixtures.traces import SESSION_ID, load_orca_session

if TYPE_CHECKING:
    from pathlib import Path


def _save(experiment_dir: Path, session_id: str, saved: SessionTraces) -> Path:
    path = (
        experiment_dir
        / execution_layout.TRACES
        / execution_layout.trace_file_name(session_id)
    )
    saved.save(path)
    return path


def _save_orca(experiment_dir: Path) -> Path:
    saved = SessionTraces.from_traces(SESSION_ID, load_orca_session().traces)
    return _save(experiment_dir, SESSION_ID, saved)


def test_reads_saved_traces_into_rows(tmp_path: Path) -> None:
    _save_orca(tmp_path)

    result = read_turns(tmp_path, SESSION_ID)

    assert not isinstance(result, Problem)
    rows = conversation_rows(result)
    assert len(rows) == len(load_orca_session().traces)
    assert [row["turn"] for row in rows] == list(range(1, len(rows) + 1))
    assert all(isinstance(row["user"], str) for row in rows)


def test_missing_file_is_a_problem(tmp_path: Path) -> None:
    result = read_turns(tmp_path, SESSION_ID)

    assert isinstance(result, Problem)
    assert result.kind == "missing"


def test_corrupt_file_is_a_problem_not_a_crash(tmp_path: Path) -> None:
    path = _save_orca(tmp_path)
    path.write_text(path.read_text(encoding="utf-8")[:40], encoding="utf-8")

    result = read_turns(tmp_path, SESSION_ID)

    assert isinstance(result, Problem)
    assert result.kind == "unsupported"


def test_unsupported_schema_version_is_a_problem(tmp_path: Path) -> None:
    path = _save_orca(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")

    result = read_turns(tmp_path, SESSION_ID)

    assert isinstance(result, Problem)
    assert result.kind == "unsupported"
    assert "schema_version" in result.detail


def test_file_for_another_session_is_a_problem(tmp_path: Path) -> None:
    other = SessionTraces.from_traces("someone-else", load_orca_session().traces)
    _save(tmp_path, SESSION_ID, other)

    result = read_turns(tmp_path, SESSION_ID)

    assert isinstance(result, Problem)
    assert result.kind == "unsupported"
    assert "someone-else" in result.detail


def test_unreadable_payload_is_shown_not_blanked() -> None:
    root = Observation(id="o1", trace_id="t1", type="SPAN", input="q", output=None)
    trace = Trace(id="t1", session_id="s", observations=(root,))

    (row,) = conversation_rows(turns((trace,)))

    assert row["user"] == "q"
    assert str(row["target"]).startswith("[unreadable: missing")
    assert row["errors"] == ["the target returned no reply"]


@pytest.mark.parametrize(
    ("saved", "recorded", "note"),
    [
        (3, 4, "3 of 4 recorded turns have traces"),
        (4, 4, None),
        (4, None, None),
    ],
)
def test_turn_count_note(saved: int, recorded: int | None, note: str | None) -> None:
    assert turn_count_note(saved, recorded) == note


def test_missing_file_problem_names_the_file_not_the_local_path(
    tmp_path: Path,
) -> None:
    result = read_turns(tmp_path, SESSION_ID)

    assert isinstance(result, Problem)
    assert execution_layout.trace_file_name(SESSION_ID) in result.detail
    assert str(tmp_path) not in result.detail


def test_unreadable_row_problem_says_which_field(tmp_path: Path) -> None:
    path = _save_orca(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["traces"][0]["observations"][0]["id"]
    path.write_text(json.dumps(data), encoding="utf-8")

    result = read_turns(tmp_path, SESSION_ID)

    assert isinstance(result, Problem)
    assert result.kind == "unsupported"
    assert "id" in result.detail
    assert "Field required" in result.detail
    assert str(tmp_path) not in result.detail


def _turn(index: int, user: str, reply: str | None) -> Trace:
    root = Observation(
        id=f"o{index}", trace_id=f"t{index}", type="SPAN", input=user, output=reply
    )
    return Trace(id=f"t{index}", session_id="any", observations=(root,))


@pytest.fixture
def experiment_root(tmp_path: Path) -> Path:
    root = tmp_path / "experiment"
    write_experiment(root, grader_records())
    return root


def _report(root: Path, records: list[Any] | None = None) -> dict[str, Any]:
    sources = load_report_sources(root)
    assert sources is not None
    specification, trials = sources
    results = EvaluationResults(
        run_id="run-1", records=grader_records() if records is None else records
    )
    data = build_report(specification, results, trial_outcomes=trials)
    return Report.model_validate(data).model_dump(by_alias=True)


def _trial(report: dict[str, Any], trial_id: str) -> dict[str, Any]:
    (trial,) = [item for item in report["trials"]["items"] if item["id"] == trial_id]
    return trial


def test_trial_shows_each_saved_turn(experiment_root: Path) -> None:
    save_trial_traces(
        experiment_root,
        "T-1-1",
        [
            _turn(1, "hello", "hi there"),
            _turn(2, "and?", "more"),
            _turn(3, "bye", None),
        ],
    )

    trial = _trial(_report(experiment_root), "T-1-1")

    assert trial["conversation"] == [
        {"turn": 1, "user": "hello", "target": "hi there", "errors": []},
        {"turn": 2, "user": "and?", "target": "more", "errors": []},
        {
            "turn": 3,
            "user": "bye",
            "target": "[unreadable: missing: no value]",
            "errors": ["the target returned no reply"],
        },
    ]
    assert trial["conversationProblem"] is None
    assert trial["turnCountNote"] is None


def test_trial_with_fewer_saved_turns_than_recorded_has_a_note(
    experiment_root: Path,
) -> None:
    save_trial_traces(
        experiment_root, "T-1-1", [_turn(1, "hello", "hi"), _turn(2, "bye", "ok")]
    )

    trial = _trial(_report(experiment_root), "T-1-1")

    assert len(trial["conversation"]) == 2
    assert trial["turnCountNote"] == "2 of 3 recorded turns have traces"


def _missing(root: Path) -> None:
    return None


def _corrupt(root: Path) -> None:
    path = save_trial_traces(root, "T-1-1", [_turn(1, "hello", "hi")])
    path.write_text(path.read_text(encoding="utf-8")[:40], encoding="utf-8")


def _other_session(root: Path) -> None:
    path = save_trial_traces(root, "T-1-1", [_turn(1, "hello", "hi")])
    SessionTraces.from_traces("someone-else", [_turn(1, "hello", "hi")]).save(path)


@pytest.mark.parametrize(
    ("make_file", "reason"),
    [
        (_missing, r"^no saved traces \(T-1-1\.json\)$"),
        (_corrupt, r"^cannot read T-1-1\.json: "),
        (_other_session, r"holds session 'someone-else', not 'T-1-1'"),
    ],
    ids=["missing", "corrupt", "other-session"],
)
def test_trial_without_readable_traces_gives_the_reason(
    experiment_root: Path, make_file: Any, reason: str
) -> None:
    make_file(experiment_root)

    report = _report(experiment_root)
    trial = _trial(report, "T-1-1")

    assert trial["conversation"] == []
    assert re.search(reason, trial["conversationProblem"])
    assert str(experiment_root) not in trial["conversationProblem"]
    assert trial["turnCountNote"] is None


def test_trial_without_a_session_gives_the_reason(experiment_root: Path) -> None:
    record = trial_record("T-1", 1).model_copy(update={"target_session_id": None})
    path = experiment_root / "outputs/trials/T-1-1/record.json"
    path.write_text(record.model_dump_json())

    trial = _trial(_report(experiment_root), "T-1-1")

    assert trial["conversation"] == []
    assert trial["conversationProblem"] == "the trial record names no target session"


def test_trial_without_grader_records_keeps_its_conversation_tab(
    experiment_root: Path,
) -> None:
    save_trial_traces(experiment_root, "T-2-1", [_turn(1, "hello", "hi")])
    t1_only = [record for record in grader_records() if record.task_id == "T-1"]

    report = _report(experiment_root, t1_only)

    (row,) = [row for row in report["resultTable"]["rows"] if row["task_id"] == "T-2"]
    assert row["results"] == {}
    (trial,) = [trial for trial in row["trials"] if trial["id"] == "T-2-1"]
    assert trial["conversation"][0]["target"] == "hi"


def _page_script(html: str) -> str:
    return html[html.index("<script>") + len("<script>") : html.rindex("</script>")]


def test_page_shows_the_count_note_and_the_reason(
    experiment_root: Path, tmp_path: Path
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to run the report renderer")
    save_trial_traces(
        experiment_root, "T-1-1", [_turn(1, "<b>hello</b>", "hi"), _turn(2, "x", "y")]
    )
    report = _report(experiment_root)
    page = tmp_path / "page.js"
    page.write_text(_page_script(render_report_page(report)), encoding="utf-8")
    subprocess.run([node, "--check", str(page)], check=True, capture_output=True)

    renderers = (
        REPORT_SCRIPT[
            REPORT_SCRIPT.index("const esc=") : REPORT_SCRIPT.index("const clip=")
        ]
        + REPORT_SCRIPT[
            REPORT_SCRIPT.index("const outcomeLabel=") : REPORT_SCRIPT.index(
                "const tableCases="
            )
        ]
        + REPORT_SCRIPT[
            REPORT_SCRIPT.index("const trialTrace=") : REPORT_SCRIPT.index(
                "const testCaseTraces="
            )
        ]
    )
    trials = {item["id"]: item for item in report["trials"]["items"]}
    script = (
        f'const trialResults=()=>"";{renderers}\n'
        f"const trials={json.dumps(trials)};\n"
        "process.stdout.write(JSON.stringify(Object.fromEntries("
        "Object.entries(trials).map(([id,row])=>[id,trialTrace(row)]))));"
    )
    rendered = json.loads(
        subprocess.run(
            [node, "-e", script], check=True, capture_output=True, text=True
        ).stdout
    )

    assert "2 of 3 recorded turns have traces" in rendered["T-1-1"]
    assert "&lt;b&gt;hello&lt;/b&gt;" in rendered["T-1-1"]
    assert "No conversation was recorded" not in rendered["T-1-1"]
    assert "No conversation was recorded for this trial." in rendered["T-1-2"]
    assert "no saved traces (T-1-2.json)" in rendered["T-1-2"]
