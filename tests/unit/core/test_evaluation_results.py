"""EvaluationResults: the engine-to-insights handoff file and its version guard.

Same guard pattern as TrialRecord (tests/unit/engine/test_schema_v2.py): an explicit
schema_version we cannot read fails loudly on load; a missing key takes the default.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from metis.core.reporting import (
    _EVALUATION_RESULTS_VERSION,
    EvaluationResults,
    SessionGraderResult,
    SessionReport,
    TurnGraderResult,
    TurnReport,
)


def _results(reason: str = "ok") -> EvaluationResults:
    return EvaluationResults(
        run_id="report",
        turn_results=[
            TurnReport(
                trace_id="t-1",
                session_id="s-1",
                scenario_id="task-1",
                turn_index=0,
                total_turns=1,
                input="hi",
                output="hello",
                routed_to="direct",
                graders=[
                    TurnGraderResult(
                        criterion_id="AC-1",
                        name="Turn Budget",
                        score=1.0,
                        reason=reason,
                        success=True,
                        skipped=False,
                        cost=0.01,
                    )
                ],
            )
        ],
        session_results=[
            SessionReport(
                session_id="s-1",
                graders=[
                    SessionGraderResult(
                        name="Session Efficiency",
                        score=0.7,
                        reason="fine",
                        success=True,
                        skipped=False,
                    )
                ],
            )
        ],
        routing={"total_traces": 1},
        timings={"turn_graders_seconds": 1.2},
        latency_seconds=1.2,
    )


class TestEvaluationResultsVersion:
    def test_current_version_loads(self) -> None:
        loaded = EvaluationResults.model_validate(
            {"schema_version": _EVALUATION_RESULTS_VERSION, "run_id": "r"}
        )
        assert loaded.schema_version == 2
        assert loaded.turn_results == []
        assert loaded.latency_seconds is None

    def test_missing_version_takes_the_default(self) -> None:
        loaded = EvaluationResults.model_validate({"run_id": "r"})
        assert loaded.schema_version == _EVALUATION_RESULTS_VERSION

    def test_wrong_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported schema_version 99"):
            EvaluationResults.model_validate({"schema_version": 99, "run_id": "r"})


class TestEvaluationResultsFile:
    def test_round_trips_through_a_file_as_utf8(self, tmp_path: Path) -> None:
        original = _results(reason="routed → analyst")
        path = tmp_path / "reports" / "results.json"

        original.save(path)

        assert path.read_bytes().decode("utf-8").endswith("\n")
        assert "→" in path.read_text(encoding="utf-8")
        assert EvaluationResults.load_file(path) == original

    def test_malformed_json_raises_validation_error(self, tmp_path: Path) -> None:
        path = tmp_path / "results.json"
        path.write_text("{", encoding="utf-8")
        with pytest.raises(ValidationError):
            EvaluationResults.load_file(path)

    def test_wrong_version_in_a_file_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "results.json"
        path.write_text('{"schema_version": 1, "run_id": "r"}', encoding="utf-8")
        with pytest.raises(ValidationError, match="different version of metis-engine"):
            EvaluationResults.load_file(path)

    def test_missing_file_raises_oserror(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            EvaluationResults.load_file(tmp_path / "absent.json")
