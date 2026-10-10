"""build_report() exposes the two headline scores report.html already renders
(issue #369), so a CI/CD pipeline can read a pass/fail verdict without
re-deriving it from the raw axis/trial data.
"""

from __future__ import annotations

from typing import Any

from metis.engine.reporting import _report


def _grader_row(session_id: str, scenario_id: str, *, success: bool) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "scenario_id": scenario_id,
        "graders": [
            {
                "name": "Grader1",
                "criterion_id": "c1",
                "task_id": "TC-001",
                "trial_index": 1,
                "success": success,
                "skipped": False,
                "reason": "" if success else "nope",
            }
        ],
    }


def _specification() -> dict[str, Any]:
    return {
        "product": {"name": "Test Product"},
        "tasks": [
            {
                "id": "TC-001",
                "scenario_ref": "s1",
                "persona_ref": "p1",
                "num_trials": 2,
                "criterion_refs": ["c1"],
            }
        ],
        "personas": [{"id": "p1"}],
        "scenarios": [{"id": "s1"}],
        "features": [
            {
                "id": "t1",
                "name": "Feature 1",
                "behaviours": [
                    {
                        "id": "b1",
                        "name": "Does the thing",
                        "description": "Does the thing.",
                        "measured": False,
                        "criteria": [
                            {
                                "id": "c1",
                                "description": {"given": "g", "when": "w", "then": "t"},
                                "grader_fqn": "pkg.graders.Grader1",
                            }
                        ],
                    }
                ],
            }
        ],
    }


class TestScores:
    def test_grader_pass_rate_sums_the_scenario_axis(self) -> None:
        """3 of 4 grader results pass, matching the 75% shown on axes.S."""
        test_results = [
            _grader_row("sess-1", "s1", success=True),
            _grader_row("sess-1", "s1", success=True),
            _grader_row("sess-1", "s1", success=True),
            _grader_row("sess-1", "s1", success=False),
        ]
        report = _report.build_report(
            _specification(),
            test_results,
            persona_of={"sess-1": "p1"},
        )
        assert report["scores"]["graderPassRate"] == {
            "rate": 75,
            "pass": 3,
            "ran": 4,
            "status": "pass",
        }

    def test_trial_success_matches_the_trials_summary(self) -> None:
        """1 of 2 trials succeeds — 50%, below the 70% threshold."""
        trial_outcomes = [
            {"scenario": "s1", "stopReason": "goal_achieved"},
            {"scenario": "s1", "stopReason": "max_turns_timeout"},
        ]
        report = _report.build_report(
            _specification(),
            [],
            persona_of={},
            trial_outcomes=trial_outcomes,
        )
        assert report["scores"]["trialSuccess"] == {
            "rate": 50,
            "successful": 1,
            "attempted": 2,
            "status": "fail",
        }

    def test_no_data_leaves_rate_and_status_blank(self) -> None:
        report = _report.build_report(_specification(), [], persona_of={})
        assert report["scores"]["graderPassRate"] == {
            "rate": None,
            "pass": 0,
            "ran": 0,
            "status": None,
        }
        assert report["scores"]["trialSuccess"] == {
            "rate": None,
            "successful": 0,
            "attempted": 0,
            "status": None,
        }
