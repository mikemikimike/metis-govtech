"""Retry visibility in the report payload (issue #346)."""

from __future__ import annotations

import json
from pathlib import Path

from metis.engine.reporting._models import Trial
from metis.engine.reporting._report import _load_run_records

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
    run = root / "runs" / folder
    run.mkdir(parents=True)
    (run / "record.json").write_text(json.dumps(record))


def test_a_clean_run_reports_attempt_one_and_no_failures(tmp_path: Path) -> None:
    _write_record(tmp_path, "s-p-1", _BASE)

    _, trials = _load_run_records(tmp_path)

    assert trials[0]["attempt"] == 1
    assert trials[0]["priorFailures"] == []


def test_a_retried_run_reports_its_attempt_and_its_failures(tmp_path: Path) -> None:
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

    _, trials = _load_run_records(tmp_path)

    assert trials[0]["attempt"] == 2
    assert trials[0]["priorFailures"] == [
        {
            "attempt": 1,
            "failureType": "ConsecutiveFailureEscalation",
            "turnReached": 0,
            "message": "2 consecutive turn failures",
        }
    ]


def test_trial_model_defaults_the_new_fields(tmp_path: Path) -> None:
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
    assert trial.priorFailures == []


def test_scenario_without_num_trials_plans_one_trial() -> None:
    """The report must mirror the engine's default, not the wizard's.

    metis-engine's Scenario schema defaults num_trials to 1; metis-wizard's
    domain model defaults it to 3 and always writes the field explicitly. A
    hand-written config that omits it runs once, so the plan must say one.
    """
    from metis.engine.reporting._report import build_plan

    experiment = {
        "personas": [{"id": "p"}],
        "scenarios": [{"id": "s", "persona_refs": ["p"]}],
    }

    plan = build_plan(experiment, [], {})

    scenario = plan["scenarios"][0]
    assert scenario["trials"] == 1
    assert scenario["sessionsPlanned"] == 1
