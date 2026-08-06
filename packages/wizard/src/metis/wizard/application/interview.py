"""Load and validate non-model interview settings and status copy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources

import yaml

from metis.wizard.domain.permissions import SessionStep

INTERVIEW_FILE = "interview.yaml"


class InterviewConfigError(RuntimeError):
    """The package-owned interview configuration cannot be used."""


@dataclass(frozen=True)
class InterviewConfig:
    """A complete, validated snapshot of ``interview.yaml``."""

    clarify_turn_cap: int
    statuses: Mapping[SessionStep, str]


def _error(key: str, detail: str) -> InterviewConfigError:
    return InterviewConfigError(f"{INTERVIEW_FILE} key '{key}' {detail}")


def _mapping(value: object, key: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise _error(key, "must be a mapping.")
    return value


def _required(mapping: Mapping[object, object], key: str) -> object:
    name = key.rsplit(".", maxsplit=1)[-1]
    if name not in mapping:
        raise _error(key, "is missing.")
    return mapping[name]


def _read_config_text() -> str:
    try:
        return (
            resources.files("metis.wizard")
            .joinpath(INTERVIEW_FILE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise _error("<file>", "is missing.") from exc


def load_interview_config() -> InterviewConfig:
    """Read and validate a fresh interview-configuration snapshot."""
    try:
        raw = yaml.safe_load(_read_config_text())
    except yaml.YAMLError as exc:
        raise _error("<document>", f"is not valid YAML: {exc}.") from exc

    document = _mapping(raw, "<document>")
    settings = _mapping(_required(document, "settings"), "settings")
    statuses = _mapping(_required(document, "statuses"), "statuses")

    turn_cap = _required(settings, "settings.clarify_turn_cap")
    if isinstance(turn_cap, bool) or not isinstance(turn_cap, int) or turn_cap <= 0:
        raise _error("settings.clarify_turn_cap", "must be a positive integer.")

    checked: dict[SessionStep, str] = {}
    for step in SessionStep:
        key = f"statuses.{step.value}"
        value = _required(statuses, key)
        if not isinstance(value, str) or not value.strip():
            raise _error(key, "must be a non-empty string.")
        checked[step] = value

    return InterviewConfig(clarify_turn_cap=turn_cap, statuses=checked)


def clarify_turn_cap() -> int:
    """Return the current maximum number of clarify questions."""
    return load_interview_config().clarify_turn_cap


def status_for(step: SessionStep) -> str:
    """Return the current package-owned status for an interview step."""
    return load_interview_config().statuses[step]


__all__ = [
    "INTERVIEW_FILE",
    "InterviewConfig",
    "InterviewConfigError",
    "clarify_turn_cap",
    "load_interview_config",
    "status_for",
]
