"""Tests for per-run log file routing."""

from __future__ import annotations

import logging
from pathlib import Path

from metis.engine.logging.router import LogRouter
from metis.engine.tui.tail import TailBuffer


class TestLogRouter:
    def test_creates_log_dir(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        LogRouter(log_dir=log_dir, log_format="text")
        assert log_dir.exists()

    def test_open_run_creates_file(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        router.open_run("direct-question", "cooperative", trial=1, num_trials=1)
        expected = tmp_path / "simulate-direct-question_cooperative-01.log"
        assert expected.exists()

    def test_trial_zero_padding_multi(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        router.open_run("scenario", "persona", trial=1, num_trials=10)
        expected = tmp_path / "simulate-scenario_persona-01.log"
        assert expected.exists()
        router.open_run("scenario", "persona", trial=10, num_trials=10)
        expected2 = tmp_path / "simulate-scenario_persona-10.log"
        assert expected2.exists()

    def test_process_routes_to_active_run_file(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        router.open_run("scn", "per", trial=1, num_trials=1)
        event_dict = {
            "event": "test message",
            "level": "info",
            "timestamp": "2026-08-05T10:00:00",
            "scenario_id": "scn",
            "persona_id": "per",
            "trial": 1,
        }
        router.process(None, "info", event_dict.copy())
        router.close_all()
        log_file = tmp_path / "simulate-scn_per-01.log"
        content = log_file.read_text()
        assert "test message" in content

    def test_process_sends_to_tail_buffer(self, tmp_path: Path) -> None:
        tail = TailBuffer(max_lines=10, min_level=logging.DEBUG)
        router = LogRouter(log_dir=tmp_path, log_format="text", tail_buffers={"w0": tail})
        router.open_run("scn", "per", trial=1, num_trials=1)
        event_dict = {
            "event": "tail test",
            "level": "warning",
            "timestamp": "2026-08-05T10:00:00",
            "scenario_id": "scn",
            "persona_id": "per",
            "trial": 1,
            "worker": "w0",
        }
        router.process(None, "warning", event_dict.copy())
        lines = tail.get_lines()
        assert any("tail test" in line for line in lines)

    def test_close_run_flushes(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        router.open_run("scn", "per", trial=1, num_trials=1)
        event_dict = {
            "event": "flush test",
            "level": "debug",
            "timestamp": "2026-08-05T10:00:00",
            "scenario_id": "scn",
            "persona_id": "per",
            "trial": 1,
        }
        router.process(None, "debug", event_dict.copy())
        router.close_run("scn", "per", trial=1)
        log_file = tmp_path / "simulate-scn_per-01.log"
        content = log_file.read_text()
        assert "flush test" in content

    def test_json_format(self, tmp_path: Path) -> None:
        import json

        router = LogRouter(log_dir=tmp_path, log_format="json")
        router.open_run("scn", "per", trial=1, num_trials=1)
        event_dict = {
            "event": "json test",
            "level": "info",
            "timestamp": "2026-08-05T10:00:00",
            "scenario_id": "scn",
            "persona_id": "per",
            "trial": 1,
        }
        router.process(None, "info", event_dict.copy())
        router.close_all()
        log_file = tmp_path / "simulate-scn_per-01.log"
        line = log_file.read_text().strip()
        parsed = json.loads(line)
        assert parsed["event"] == "json test"
