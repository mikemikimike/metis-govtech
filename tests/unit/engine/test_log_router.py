"""Tests for per-run log file routing."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import structlog

from metis.engine.logging.router import LogRouter
from metis.engine.tui.tail import TailBuffer

# ISO-8601 UTC wall clock trimmed to whole seconds + Z, then (+HH:MM:SS) elapsed
_TAIL_PREFIX = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z \(\+\d{2}:\d{2}:\d{2}\) "
)


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

    def test_reopened_run_replaces_old_log(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        router.open_run("scn", "per", trial=1, num_trials=1)
        self._process(
            router,
            {
                "event": "old attempt",
                "level": "info",
                "scenario_id": "scn",
                "persona_id": "per",
                "trial": 1,
            },
        )
        router.close_run("scn", "per", trial=1)
        router.open_run("scn", "per", trial=1, num_trials=1)
        self._process(
            router,
            {
                "event": "new attempt",
                "level": "info",
                "scenario_id": "scn",
                "persona_id": "per",
                "trial": 1,
            },
        )
        router.close_run("scn", "per", trial=1)
        content = (tmp_path / "simulate-scn_per-01.log").read_text()
        assert "old attempt" not in content
        assert "new attempt" in content

    def test_trial_zero_padding_multi(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        router.open_run("scenario", "persona", trial=1, num_trials=10)
        expected = tmp_path / "simulate-scenario_persona-01.log"
        assert expected.exists()
        router.open_run("scenario", "persona", trial=10, num_trials=10)
        expected2 = tmp_path / "simulate-scenario_persona-10.log"
        assert expected2.exists()

    def _process(self, router: LogRouter, event_dict: dict) -> None:
        """Call router.process, expecting DropEvent when no fallback renderer."""
        import pytest

        with pytest.raises(structlog.DropEvent):
            router.process(None, event_dict.get("level", "info"), event_dict.copy())

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
        self._process(router, event_dict)
        router.close_all()
        log_file = tmp_path / "simulate-scn_per-01.log"
        content = log_file.read_text()
        assert "test message" in content

    def test_process_sends_to_tail_buffer(self, tmp_path: Path) -> None:
        tail = TailBuffer(max_lines=10, min_level=logging.DEBUG)
        router = LogRouter(
            log_dir=tmp_path, log_format="text", tail_buffers={"w0": tail}
        )
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
        self._process(router, event_dict)
        lines = tail.get_lines()
        assert any("tail test" in line for line in lines)
        matching = [line for line in lines if "tail test" in line]
        assert matching, "tail line missing"
        assert _TAIL_PREFIX.match(matching[0]), (
            f"tail prefix not ISO-8601 Z + (+elapsed): {matching[0]!r}"
        )

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
        self._process(router, event_dict)
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
        self._process(router, event_dict)
        router.close_all()
        log_file = tmp_path / "simulate-scn_per-01.log"
        line = log_file.read_text().strip()
        parsed = json.loads(line)
        assert parsed["event"] == "json test"

    def test_wall_clock_str_trims_fractional_and_keeps_z(self, tmp_path: Path) -> None:
        router = LogRouter(log_dir=tmp_path, log_format="text")
        # production-typical: fractional seconds + Z -> trimmed to whole seconds + Z
        assert (
            router._wall_clock_str("2026-09-02T00:51:17.138406Z")
            == "2026-09-02T00:51:17Z"
        )
        # no fractional, no Z -> whole seconds + Z appended
        assert router._wall_clock_str("2026-08-05T10:00:00") == "2026-08-05T10:00:00Z"
        # empty/absent -> empty string, no raise
        assert router._wall_clock_str("") == ""
