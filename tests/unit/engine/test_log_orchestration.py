"""Tests for orchestration log (simulate.log)."""

from pathlib import Path

from metis.engine.logging.orchestration import OrchestrationLogger


class TestOrchestrationLogger:
    def test_creates_simulate_log(self, tmp_path: Path) -> None:
        orch = OrchestrationLogger(log_dir=tmp_path)
        orch.close()
        assert (tmp_path / "simulate.log").exists()

    def test_scenario_started(self, tmp_path: Path) -> None:
        orch = OrchestrationLogger(log_dir=tmp_path)
        orch.scenario_started("direct-question")
        orch.close()
        content = (tmp_path / "simulate.log").read_text()
        assert "SCENARIO direct-question STARTED" in content

    def test_run_started_includes_log_pointer(self, tmp_path: Path) -> None:
        orch = OrchestrationLogger(log_dir=tmp_path)
        orch.run_started("direct-question", "cooperative", trial=1, num_trials=1)
        orch.close()
        content = (tmp_path / "simulate.log").read_text()
        assert "RUN direct-question x cooperative [trial 1/1] STARTED" in content
        assert "simulate-direct-question_cooperative-01.log" in content

    def test_run_completed(self, tmp_path: Path) -> None:
        orch = OrchestrationLogger(log_dir=tmp_path)
        orch.run_completed(
            "direct-question",
            "cooperative",
            trial=1,
            num_trials=1,
            stop_reason="goal_achieved",
            total_turns=3,
            duration_seconds=226.0,
        )
        orch.close()
        content = (tmp_path / "simulate.log").read_text()
        assert "RUN direct-question x cooperative [trial 1/1] COMPLETED" in content
        assert "goal_achieved" in content
        assert "3 turns" in content

    def test_scenario_completed(self, tmp_path: Path) -> None:
        orch = OrchestrationLogger(log_dir=tmp_path)
        orch.scenario_completed("direct-question", runs_passed=1, runs_total=1)
        orch.close()
        content = (tmp_path / "simulate.log").read_text()
        assert "SCENARIO direct-question COMPLETED (1/1 runs passed)" in content

    def test_json_format(self, tmp_path: Path) -> None:
        import json

        orch = OrchestrationLogger(log_dir=tmp_path, log_format="json")
        orch.scenario_started("scn")
        orch.close()
        content = (tmp_path / "simulate.log").read_text().strip()
        parsed = json.loads(content)
        assert parsed["event_type"] == "SCENARIO_STARTED"
        assert parsed["scenario_id"] == "scn"

    def test_resume_appends_and_records_plan(self, tmp_path: Path) -> None:
        first = OrchestrationLogger(log_dir=tmp_path)
        first.scenario_started("old")
        first.close()

        resumed = OrchestrationLogger(log_dir=tmp_path, append=True)
        resumed.resume_started(redo_count=2, complete_count=3)
        resumed.close()

        content = (tmp_path / "simulate.log").read_text()
        assert "SCENARIO old STARTED" in content
        assert "RESUME STARTED (2 runs to redo, 3 already complete)" in content
