"""Harness configuration — loads YAML + env credentials."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Authentication configuration."""

    username: str
    password: str
    login_button_text: str = "Log in with WOG AD"
    userid_button_text: str = "Log in with user ID"
    signin_button_text: str = "Sign in"


class TimeoutConfig(BaseModel):
    """Timeout settings for page and response waits."""

    response_wait_ms: int = 300_000
    page_load_ms: int = 10_000


class HarnessConfig(BaseModel):
    """Top-level harness config combining YAML file + env vars."""

    url: str
    auth: AuthConfig
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> HarnessConfig:
        """Load from YAML, injecting credentials from environment.

        :param path: Path to config YAML. Defaults to config.yaml alongside this module.
        """
        if path is None:
            path = Path(__file__).parent / "config.yaml"
        raw = yaml.safe_load(path.read_text())
        raw["url"] = os.environ["ORCA_URL"]
        raw.setdefault("auth", {})
        raw["auth"]["username"] = os.environ["ORCA_USERNAME"]
        raw["auth"]["password"] = os.environ["ORCA_PASSWORD"]
        return cls.model_validate(raw)
