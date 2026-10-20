"""Playwright runner configuration — loads YAML + env credentials."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr


class AuthConfig(BaseModel):
    """Authentication configuration."""

    username: str
    password: SecretStr
    login_button_text: str = "Log in with WOG AD"
    userid_button_text: str = "Log in with user ID"
    signin_button_text: str = "Sign in"


class TimeoutConfig(BaseModel):
    """Timeout settings for page and response waits."""

    response_wait_ms: int = 300_000
    page_load_ms: int = 10_000


class RetryConfig(BaseModel):
    """Retry configuration for simulation resilience."""

    action_max_attempts: int = 3
    action_backoff_base_seconds: float = 1.0
    action_backoff_max_seconds: float = 10.0
    turn_max_retries: int = 1
    consecutive_turn_failures_limit: int = 2
    trial_max_retries: int = 2
    trial_retry_delay_seconds: float = 5.0


class OrcaPlaywrightRunnerConfig(BaseModel):
    """OrcaPlaywright runner configuration — YAML file + env vars."""

    url: str
    auth: AuthConfig
    headed: bool = False
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> OrcaPlaywrightRunnerConfig:
        """Load from YAML, injecting credentials and flags from environment.

        :param path: Path to config YAML. Defaults to config.yaml alongside this module.
        """
        if path is None:
            path = Path(__file__).parent / "config.yaml"
        required_vars = ("ORCA_URL", "ORCA_USERNAME", "ORCA_PASSWORD")
        missing = [v for v in required_vars if v not in os.environ]
        if missing:
            raise ValueError(
                f"Playwright runner requires environment variables: {', '.join(missing)}. "
                "Set them in .env or export them before running a simulation."
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw["url"] = os.environ["ORCA_URL"]
        raw.setdefault("auth", {})
        raw["auth"]["username"] = os.environ["ORCA_USERNAME"]
        raw["auth"]["password"] = os.environ["ORCA_PASSWORD"]
        raw["headed"] = os.environ.get("HEADED", "").lower() == "true"
        return cls.model_validate(raw)
