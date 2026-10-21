"""Tests for RetryConfig and OrcaPlaywrightRunnerConfig.retry field."""

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.gen_1.runners.orca_playwright._config import (
    OrcaPlaywrightRunnerConfig,
    RetryConfig,
)


class TestRetryConfig:
    def test_defaults(self) -> None:
        rc = RetryConfig()
        assert rc.action_max_attempts == 3
        assert rc.action_backoff_base_seconds == 1.0
        assert rc.action_backoff_max_seconds == 10.0
        assert rc.turn_max_retries == 1
        assert rc.consecutive_turn_failures_limit == 2
        assert rc.trial_max_retries == 2
        assert rc.trial_retry_delay_seconds == 5.0

    def test_custom_values(self) -> None:
        rc = RetryConfig(action_max_attempts=5, trial_max_retries=1)
        assert rc.action_max_attempts == 5
        assert rc.trial_max_retries == 1


class TestOrcaPlaywrightRunnerConfigRetryField:
    def test_retry_defaults_when_not_specified(self) -> None:
        config = OrcaPlaywrightRunnerConfig(
            url="http://example.com",
            auth={"username": "u", "password": "p"},
        )
        assert config.retry is not None
        assert config.retry.action_max_attempts == 3

    def test_retry_can_be_overridden(self) -> None:
        config = OrcaPlaywrightRunnerConfig(
            url="http://example.com",
            auth={"username": "u", "password": "p"},
            retry={"trial_max_retries": 0},
        )
        assert config.retry.trial_max_retries == 0
