"""Orca API runner configuration — loads YAML + env credentials."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field

from ...config import RunRetryConfig

ENV_URL = "ORCA_API_URL"
ENV_KEY = "ORCA_API_KEY"


def _require_env() -> tuple[str, str]:
    """Read both variables, reporting every missing one in a single message."""
    values = {name: os.environ.get(name, "").strip() for name in (ENV_URL, ENV_KEY)}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(
            f"Orca API runner is missing required environment "
            f"variable(s): {', '.join(missing)}"
        )
    url = values[ENV_URL]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(
            f"Orca API runner: {ENV_URL} must be an http(s) URL, got {url!r}"
        )
    return url, values[ENV_KEY]


class OrcaApiRunnerConfig(BaseModel):
    """Runner config: YAML-tunable knobs plus credentials from the environment."""

    base_url: str
    api_key: str
    poll_interval_ms: int = 3000
    submit_rpm: int = 6
    store_retry_window_s: float = 30.0
    delete_session_on_teardown: bool = False
    retry: RunRetryConfig = Field(default_factory=RunRetryConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> OrcaApiRunnerConfig:
        if path is None:
            path = Path(__file__).parent / "config.yaml"
        base_url, api_key = _require_env()
        raw = yaml.safe_load(path.read_text()) or {}
        raw["base_url"] = base_url
        raw["api_key"] = api_key
        return cls.model_validate(raw)
