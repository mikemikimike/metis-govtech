"""Process-wide settings and the production composition of the wizard dependencies.

The app keeps immutable settings and model clients for the lifetime of the process. It keeps no
user Profile, pending request, or Interview state — every lifecycle request carries the required
state in its body. `build_dependencies` is the one place that constructs the real gateway-backed
interviewer and matcher; tests inject a scripted pair instead through the router's dependency
override.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from metis.wizard import InterviewRequest, InterviewResult


class SettingsError(RuntimeError):
    """A required setting is missing from the environment."""


@dataclass(frozen=True)
class Settings:
    """The three environment-backed settings the service needs to reach the model gateway."""

    api_key: str
    base_url: str
    judge_model: str

    @classmethod
    def from_env(cls) -> Settings:
        """Read settings from the environment, naming any that are missing."""
        api_key = os.environ.get("API_KEY", "")
        base_url = os.environ.get("BASE_URL", "")
        judge_model = os.environ.get("JUDGE_MODEL", "")
        missing = [
            name
            for name, value in (
                ("API_KEY", api_key),
                ("BASE_URL", base_url),
                ("JUDGE_MODEL", judge_model),
            )
            if not value
        ]
        if missing:
            raise SettingsError(
                f"The API needs {', '.join(missing)} in the environment."
            )
        return cls(api_key=api_key, base_url=base_url, judge_model=judge_model)


InterviewHandler: TypeAlias = Callable[[InterviewRequest], InterviewResult]


@dataclass(frozen=True)
class WizardDependencies:
    """The configured public Interview handler used by the API routes."""

    interview_handler: InterviewHandler


def build_dependencies(settings: Settings) -> WizardDependencies:
    """Compose the production interviewer and matcher from settings.

    The wizard package owns provider construction. The API passes only normalized settings to the
    public runtime configurator and keeps the public `handle_interview` function as its handler.
    """
    from metis.wizard import configure_interview_runtime, handle_interview

    configure_interview_runtime(
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.judge_model,
    )
    return WizardDependencies(interview_handler=handle_interview)


__all__ = [
    "Settings",
    "SettingsError",
    "InterviewHandler",
    "WizardDependencies",
    "build_dependencies",
]
