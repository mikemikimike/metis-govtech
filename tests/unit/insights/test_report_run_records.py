"""The report reads each trial's record.json through TrialRecord (issues #346, #423)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from structlog.testing import capture_logs

from metis.core.trials import TrialConfig, TrialFailure, TrialOutcome, TrialRecord
from metis.core.report import Trial
from metis.insights._report import _load_trial_records

if TYPE_CHECKING:
    from pathlib import Path


def _record(stop_reason: str = "goal_achieved", **fields: object) -> TrialRecord:
    return TrialRecord(
        config=TrialConfig(persona="p", scenario="s"),
        outcome=TrialOutcome(
            stop_reason=stop_reason, total_turns=2, duration_seconds=3.0
        ),
        target_session_id="sess-1",
        **fields,  # type: ignore[arg-type]
    )


def _write(root: Path, folder: str, data: dict[str, Any]) -> None:
    trial = root / "outputs" / "trials" / folder
    trial.mkdir(parents=True)
    (trial / "record.json").write_text(json.dumps(data))


def _write_record(root: Path, folder: str, record: TrialRecord) -> None:
    """Write *record* the way the engine's ``_save_trial_record`` does."""
    _write(root, folder, record.model_dump())


def test_an_engine_written_record_round_trips(tmp_path: Path) -> None:
    _write_record(tmp_path, "s-p-1", _record())

    persona_of, trials = _load_trial_records(tmp_path)

    assert persona_of == {"sess-1": "p"}
    [trial] = trials
    assert trial["persona"] == "p"
    assert trial["scenario"] == "s"
    assert trial["session"] == "sess-1"
    assert trial["turns"] == 2
    assert trial["duration"] == 3.0
    assert trial["attempt"] == 1
    assert trial["stopReason"] == "goal_achieved"
    assert trial["failureSource"] == "outcome"
    assert trial["conversation"] == []


def test_a_retried_trial_reports_its_attempt(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "s-p-1",
        _record(
            attempt_number=2,
            max_allowed_attempts=3,
            prior_failures=[
                TrialFailure(
                    attempt_number=1,
                    failure_type="ConsecutiveFailureEscalation",
                    turn_reached=0,
                    error_message="2 consecutive turn failures",
                    duration_ms=642000,
                )
            ],
        ),
    )

    _, trials = _load_trial_records(tmp_path)

    assert trials[0]["attempt"] == 2
    assert "priorFailures" not in trials[0]


def test_trial_model_defaults_the_attempt_field() -> None:
    """Reports written before this change must still parse."""
    trial = Trial(
        id="s-p-1",
        session="sess-1",
        persona="p",
        scenario="s",
        stopReason="goal_achieved",
        message="goal_achieved",
        failureSource="outcome",
        turns=2,
        category="succeeded",
    )

    assert trial.attempt == 1


def test_task_plan_uses_the_selected_trial_count() -> None:
    from metis.insights._report import build_plan

    specification = {
        "personas": [{"id": "p"}],
        "tasks": [
            {
                "id": "TC-001",
                "scenario_ref": "s",
                "persona_ref": "p",
                "num_trials": 1,
                "behaviour_refs": ["B-1"],
            }
        ],
    }
    task = build_plan(specification, [], {"TC-001": {"AC-1"}})["tasks"][0]
    assert task["trials"] == task["trialsPlanned"] == 1


def test_an_invalid_record_is_skipped_not_fatal(tmp_path: Path) -> None:
    valid = _record().model_dump()
    _write(tmp_path, "s-p-1", valid)
    _write(tmp_path, "s-p-2", {**valid, "schema_version": 99})
    _write(
        tmp_path,
        "s-p-3",
        {**valid, "outcome": {"stop_reason": "max_turns", "total_turns": 1}},
    )

    with capture_logs() as logs:
        _, trials = _load_trial_records(tmp_path)

    assert [t["id"] for t in trials] == ["s-p-1"]
    skipped = [e for e in logs if e["event"] == "record_unreadable"]
    assert len(skipped) == 2
    assert {e["log_level"] for e in skipped} == {"warning"}


def test_a_legacy_conversation_key_is_ignored(tmp_path: Path) -> None:
    """A record written before #461 still has `conversation`. It loads, and its
    per-turn notices no longer feed the trial-trace view or the blame."""
    data = _record(stop_reason="max_turns").model_dump()
    data["conversation"] = [
        {
            "turn_number": 1,
            "target_response": {"response_notices": ["Turn failed"]},
        }
    ]
    _write(tmp_path, "s-p-1", data)

    _, [trial] = _load_trial_records(tmp_path)

    assert trial["conversation"] == []
    assert trial["failureSource"] == "evaluationRunner"
    assert trial["message"] == "max_turns"
