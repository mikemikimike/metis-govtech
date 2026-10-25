"""Process-wide settings and the production composition of the wizard dependencies.

The app keeps immutable settings and model clients for the lifetime of the process. It keeps no
user Specification, pending request, or Interview state — every lifecycle request carries the required
state in its body. `build_dependencies` is the one place that constructs the real gateway-backed
interviewer and matcher; tests inject a scripted pair instead through the router's dependency
override.

The API starts when model settings are missing. Then `GET /api/v1/models` reports the missing
roles, and each Interview route returns 503 `model_unavailable`.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from metis.core.model_settings import (
    ModelRole,
    RoleSettings,
    find_env_file,
    format_missing_settings,
    missing_settings,
    resolve_role,
)
from metis.wizard import InterviewRequest, InterviewResult

if TYPE_CHECKING:
    from pathlib import Path

API_ROLES = (ModelRole.INTERVIEW,)
"""The roles that the API cannot run an Interview without. Embeddings are optional."""


class SettingsError(RuntimeError):
    """A required setting is missing from the environment."""


@dataclass(frozen=True)
class Settings:
    """The environment that the API reads its model settings from."""

    env: Mapping[str, str]
    env_file: Path | None = None

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        """Take a copy of the process environment."""
        return cls(env=dict(os.environ), env_file=env_file or find_env_file())

    def role(self, role: ModelRole) -> RoleSettings:
        return resolve_role(role, self.env)

    def missing_message(self) -> str | None:
        """The error text when the interview role has no key, else ``None``."""
        missing = missing_settings(API_ROLES, self.env)
        if not missing:
            return None
        return format_missing_settings("The METIS API", missing, self.env_file)


InterviewHandler: TypeAlias = Callable[[InterviewRequest], InterviewResult]


@dataclass(frozen=True)
class WizardDependencies:
    """The configured public Interview handler used by the API routes."""

    interview_handler: InterviewHandler


def build_dependencies(settings: Settings) -> WizardDependencies:
    """Compose the production interviewer and matcher from settings.

    The wizard package owns provider construction. The API passes only the resolved role settings
    to the public runtime configurator and keeps the public `handle_interview` function as its
    handler.

    Raises ``SettingsError`` when the interview role has no API key.
    """
    message = settings.missing_message()
    if message is not None:
        raise SettingsError(message)

    from metis.wizard import configure_interview_runtime, handle_interview

    configure_interview_runtime(
        interview=settings.role(ModelRole.INTERVIEW),
        embeddings=settings.role(ModelRole.EMBEDDINGS),
    )
    return WizardDependencies(interview_handler=handle_interview)


__all__ = [
    "API_ROLES",
    "InterviewHandler",
    "Settings",
    "SettingsError",
    "WizardDependencies",
    "build_dependencies",
]
