"""Tests for metis.core.logging module."""

import json
import logging
import os
import re
from unittest.mock import patch

import structlog

from metis.core.logging import configure_logging, get_logger


class TestGetLogger:
    def test_returns_bound_logger(self):
        log = get_logger("test.module")
        assert hasattr(log, "info")
        assert hasattr(log, "warning")
        assert hasattr(log, "error")
        assert hasattr(log, "debug")
        assert hasattr(log, "bind")

    def test_infers_name_when_none(self):
        log = get_logger()
        assert log is not None


class TestConfigureLogging:
    def setup_method(self):
        structlog.reset_defaults()
        root = logging.getLogger()
        root.handlers.clear()

    def test_sets_log_level(self):
        configure_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_level_from_env_var(self):
        with patch.dict(os.environ, {"METIS_LOG_LEVEL": "WARNING"}):
            configure_logging()
            root = logging.getLogger()
            assert root.level == logging.WARNING

    def test_explicit_level_overrides_env_var(self):
        with patch.dict(os.environ, {"METIS_LOG_LEVEL": "WARNING"}):
            configure_logging(level="DEBUG")
            root = logging.getLogger()
            assert root.level == logging.DEBUG

    def test_json_output(self, capsys):
        configure_logging(level="INFO", json=True)
        log = get_logger("test.json")
        log.info("hello", key="value")

        captured = capsys.readouterr()
        line = captured.err.strip().split("\n")[-1]
        parsed = json.loads(line)
        assert parsed["event"] == "hello"
        assert parsed["key"] == "value"
        assert parsed["level"] == "info"

    def test_pretty_output_to_stderr(self, capsys):
        configure_logging(level="INFO", pretty=True)
        log = get_logger("test.pretty")
        log.info("hello_event", key="value")

        captured = capsys.readouterr()
        assert "hello_event" in captured.err
        assert captured.out == ""

    def test_default_level_is_warning(self):
        configure_logging()
        root = logging.getLogger()
        assert root.level == logging.WARNING


class TestStructlogLevelFiltering:
    """Verify that structlog's own processor chain respects the configured level."""

    def setup_method(self):
        structlog.reset_defaults()
        root = logging.getLogger()
        root.handlers.clear()

    def test_debug_events_dropped_at_warning_level(self, capsys):
        configure_logging(level="WARNING", json=True)
        log = get_logger("test.filter")
        log.debug("should_not_appear")

        captured = capsys.readouterr()
        assert "should_not_appear" not in captured.err

    def test_info_events_pass_at_info_level(self, capsys):
        configure_logging(level="INFO", json=True)
        log = get_logger("test.filter")
        log.info("should_appear")

        captured = capsys.readouterr()
        assert "should_appear" in captured.err

    def test_all_events_pass_at_debug_level(self, capsys):
        configure_logging(level="DEBUG", json=True)
        log = get_logger("test.filter")
        log.debug("debug_visible")

        captured = capsys.readouterr()
        assert "debug_visible" in captured.err


class TestPublicExports:
    def test_logging_importable_from_metis_core(self):
        from metis.core import configure_logging, get_logger

        assert callable(get_logger)
        assert callable(configure_logging)

    def test_console_importable_from_metis_core(self):
        from rich.console import Console

        from metis.core import console

        assert isinstance(console, Console)


class TestIsoTimestamp:
    # iso_timestamp() always emits 6-digit microseconds and a literal Z, e.g.
    # 2026-09-02T03:27:51.790384Z
    ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    # structlog's TimeStamper(fmt="iso") renders the same shape but omits the
    # fractional part when the microsecond is exactly 0, so the fraction is
    # optional when matching structlog's output.
    STRUCTLOG_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z$")

    def test_helper_shape(self):
        from metis.core.logging import iso_timestamp

        assert self.ISO_RE.match(iso_timestamp())

    def test_matches_structlog_timestamper_format(self):
        """Consistency guard: iso_timestamp() and structlog's
        TimeStamper(fmt="iso") render UTC ISO-8601 with a Z suffix the same
        way, so a structlog upgrade that changes ISO rendering fails CI.
        Compare structure, not the exact instant.
        """
        from metis.core.logging import iso_timestamp

        stamper = structlog.processors.TimeStamper(fmt="iso")
        structlog_ts = stamper(None, "info", {})["timestamp"]

        ours = iso_timestamp()

        # Our helper always emits 6-digit microseconds...
        assert self.ISO_RE.match(ours)
        # ...and structlog renders the same canonical shape (fraction optional
        # only when microsecond == 0), both ending in Z.
        assert self.STRUCTLOG_ISO_RE.match(structlog_ts)
        assert ours.endswith("Z")
        assert structlog_ts.endswith("Z")
