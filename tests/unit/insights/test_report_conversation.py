"""Reading a trial's conversation from the traces `evaluate` saved (#462)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from metis.core import SessionTraces, execution_layout
from metis.core.trace_processing import Problem, turns
from metis.core.traces import Observation, Trace
from metis.insights._conversation import conversation_rows, read_turns, turn_count_note
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
