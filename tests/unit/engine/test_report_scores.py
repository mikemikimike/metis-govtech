"""build_report() exposes the two headline scores report.html already renders
(issue #369), so a CI/CD pipeline can read a pass/fail verdict without
re-deriving it from the raw axis/trial data.
"""

from __future__ import annotations

from typing import Any

import pytest

from metis.engine.reporting import _report


@pytest.fixture(autouse=True)
def _stub_display_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the real metric-class import; only the display name matters here."""
    monkeypatch.setattr(
        _report,
        "display_names",
        lambda fqns: ({fqn: "Metric1" for fqn in fqns}, []),
    )


def _metric_row(session_id: str, scenario_id: str, *, success: bool) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "scenario_id": scenario_id,
        "metrics": [
            {
                "name": "Metric1",
                "success": success,
                "skipped": False,
                "reason": "" if success else "nope",
            }
        ],
    }


def _profile() -> dict[str, Any]:
    return {
        "product": {"name": "Test Product"},
        "personas": [{"id": "p1"}],
        "scenarios": [{"id": "s1", "behaviour_refs": ["b1"]}],
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
                                "metric_fqn": "pkg.metrics.Metric1",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _experiment() -> dict[str, Any]:
    return {
        "personas": [{"id": "p1"}],
        "scenarios": [
            {
                "id": "s1",
                "persona_refs": ["p1"],
                "num_trials": 2,
                "metric_refs": ["pkg.metrics.Metric1"],
            }
        ],
    }


class TestScores:
    def test_metric_pass_rate_sums_the_scenario_axis(self) -> None:
        """3 of 4 metric results pass, matching the 75% shown on axes.S."""
        test_results = [
            _metric_row("sess-1", "s1", success=True),
            _metric_row("sess-1", "s1", success=True),
            _metric_row("sess-1", "s1", success=True),
            _metric_row("sess-1", "s1", success=False),
        ]
        report = _report.build_report(
            _profile(),
            _experiment(),
            test_results,
            persona_of={"sess-1": "p1"},
        )
        assert report["scores"]["metricPassRate"] == {
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
            _profile(),
            _experiment(),
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
        report = _report.build_report(_profile(), _experiment(), [], persona_of={})
        assert report["scores"]["metricPassRate"] == {
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
