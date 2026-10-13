"""Retry visibility in the report payload (issue #346)."""

from __future__ import annotations

import json
from pathlib import Path

from metis.insights._models import Trial
from metis.insights._report import _load_trial_records

_BASE: dict = {
    "config": {"persona": "p", "scenario": "s"},
    "outcome": {
        "stop_reason": "goal_achieved",
        "total_turns": 2,
        "duration_seconds": 3.0,
    },
    "target_session_id": "sess-1",
    "conversation": [],
}


def _write_record(root: Path, folder: str, record: dict) -> None:
    trial = root / "trials" / folder
    trial.mkdir(parents=True)
    (trial / "record.json").write_text(json.dumps(record))


def test_a_clean_trial_reports_attempt_one(tmp_path: Path) -> None:
    _write_record(tmp_path, "s-p-1", _BASE)

    _, trials = _load_trial_records(tmp_path)

    assert trials[0]["attempt"] == 1


def test_a_retried_trial_reports_its_attempt(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "s-p-1",
        {
            **_BASE,
            "attempt_number": 2,
            "max_allowed_attempts": 3,
            "prior_failures": [
                {
                    "attempt_number": 1,
                    "failure_type": "ConsecutiveFailureEscalation",
                    "submission_phase": "unknown",
                    "turn_reached": 0,
                    "error_message": "2 consecutive turn failures",
                    "duration_ms": 642000,
                }
            ],
        },
    )

    _, trials = _load_trial_records(tmp_path)

    assert trials[0]["attempt"] == 2
    # The per-attempt detail is deliberately NOT mirrored into the report: it
    # stays in record.json, which is not a published schema, while every field
    # of report.schema.json is a contract downstream consumers audit. A record
    # carrying prior_failures must still load and must not leak them here.
    assert "priorFailures" not in trials[0]


def test_trial_model_defaults_the_attempt_field(tmp_path: Path) -> None:
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
