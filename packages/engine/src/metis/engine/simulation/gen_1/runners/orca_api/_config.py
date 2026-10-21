"""Orca API runner configuration — loads YAML + env credentials."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator

from ....config import TrialRetryConfig

ENV_URL = "ORCA_API_URL"
ENV_KEY = "ORCA_API_KEY"
#: Optional: the evaluator's own GovTech AI Platform key (see the field docs).
ENV_PLATFORM_AI_KEY = "ORCA_PLATFORM_AI_KEY"

#: The header Orca reads the platform key from, on ``POST /chat`` only.
PLATFORM_AI_KEY_HEADER = "X-PlatformAI-Key"

# Orca answers 400 for a key that is empty, outside these bounds, or contains
# whitespace — all checkable here, so a whole experiment never dies on its
# first submit for a typo.
_PLATFORM_KEY_MIN_LEN = 8
_PLATFORM_KEY_MAX_LEN = 512


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
    api_key: SecretStr
    platform_ai_key: SecretStr | None = Field(
        default=None,
        description=(
            "The evaluator's own GovTech AI Platform key, sent as"
            " X-PlatformAI-Key on POST /chat. Optional: without it every turn"
            " spends Orca's shared weekly allowance, and Orca *silently"
            " downgrades to a cheaper model* once that allowance is spent —"
            " which changes the model under test mid-experiment. With it, each"
            " turn is billed to the evaluator's own platform project on a"
            " fixed model, outside the allowance and its downgrades."
        ),
    )
    poll_interval_ms: int = 3000
    submit_rpm: int = 6
    store_retry_window_s: float = 30.0
    delete_session_on_teardown: bool = False
    insecure: bool = False
    retry: TrialRetryConfig = Field(default_factory=TrialRetryConfig)

    @field_validator("platform_ai_key")
    @classmethod
    def _check_platform_ai_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Reject locally what Orca would answer 400 for.

        The value itself never appears in the message — only which rule it
        broke — so a config error is diagnosable without leaking a credential
        into a log or a traceback.
        """
        if value is None:
            return None
        raw = value.get_secret_value()
        if not raw:
            problem = "is empty"
        elif any(char.isspace() for char in raw):
            problem = "contains whitespace"
        elif len(raw) < _PLATFORM_KEY_MIN_LEN:
            problem = f"is shorter than {_PLATFORM_KEY_MIN_LEN} characters"
        elif len(raw) > _PLATFORM_KEY_MAX_LEN:
            problem = f"is longer than {_PLATFORM_KEY_MAX_LEN} characters"
        else:
            return value
        raise ValueError(
            f"Orca API runner: {ENV_PLATFORM_AI_KEY} {problem}; "
            "Orca would reject it with a 400"
        )

    @classmethod
    def load(cls, path: Path | None = None) -> OrcaApiRunnerConfig:
        if path is None:
            path = Path(__file__).parent / "config.yaml"
        base_url, api_key = _require_env()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw["base_url"] = base_url
        raw["api_key"] = api_key
        # Optional, and unset is a legitimate mode (the shared allowance), so
        # an absent or blank variable leaves the field None rather than
        # failing validation. A set-but-malformed one is rejected above.
        platform_key = os.environ.get(ENV_PLATFORM_AI_KEY, "").strip()
        if platform_key:
            raw["platform_ai_key"] = platform_key
        return cls.model_validate(raw)
