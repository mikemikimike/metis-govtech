"""Load and validate non-model interview settings and status copy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources

import yaml

from metis.wizard.domain.permissions import InterviewStep

CONFIG_FILE = "config.yaml"


class ConfigError(RuntimeError):
    """The package-owned interview configuration cannot be used."""


@dataclass(frozen=True)
class Config:
    """A complete, validated snapshot of ``config.yaml``."""

    clarify_turn_cap: int
    opening_question: str
    statuses: Mapping[InterviewStep, str]


def _error(key: str, detail: str) -> ConfigError:
    return ConfigError(f"{CONFIG_FILE} key '{key}' {detail}")


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
            .joinpath(CONFIG_FILE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise _error("<file>", "is missing.") from exc


def load_config() -> Config:
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

    opening_question = _required(document, "opening_question")
    if not isinstance(opening_question, str) or not opening_question.strip():
        raise _error("opening_question", "must be a non-empty string.")

    if "prioritise" in statuses:
        raise _error("statuses.prioritise", "was removed and must not be present.")

    checked: dict[InterviewStep, str] = {}
    for step in InterviewStep:
        key = f"statuses.{step.value}"
        value = _required(statuses, key)
        if not isinstance(value, str) or not value.strip():
            raise _error(key, "must be a non-empty string.")
        checked[step] = value

    return Config(
        clarify_turn_cap=turn_cap,
        opening_question=opening_question,
        statuses=checked,
    )


def clarify_turn_cap() -> int:
    """Return the current maximum number of clarify questions."""
    return load_config().clarify_turn_cap


def status_for(step: InterviewStep) -> str:
    """Return the current package-owned status for an interview step."""
    return load_config().statuses[step]


def opening_question() -> str:
    """Return the package-owned question shown before the first model call."""
    return load_config().opening_question


__all__ = [
    "CONFIG_FILE",
    "Config",
    "ConfigError",
    "clarify_turn_cap",
    "load_config",
    "opening_question",
    "status_for",
]
