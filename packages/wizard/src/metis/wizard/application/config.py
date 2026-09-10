"""Load and validate non-model interview settings and status copy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources

import yaml

from metis.wizard.contracts.config import InterviewConfig, PerspectiveDefinition
from metis.wizard.contracts.interview_state import Perspective
from metis.wizard.domain.permissions import InterviewStep

CONFIG_FILE = "config.yaml"


class ConfigError(RuntimeError):
    """The package-owned interview configuration cannot be used."""


@dataclass(frozen=True)
class Config:
    """A complete, validated snapshot of ``config.yaml``."""

    clarify_turn_cap: int
    opening_question: str
    working_status: str
    statuses: Mapping[InterviewStep, str]
    perspectives: tuple[PerspectiveDefinition, ...]


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


def _sequence(value: object, key: str) -> list[object]:
    if not isinstance(value, list):
        raise _error(key, "must be a list.")
    return value


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

    perspective_values = _sequence(_required(document, "perspectives"), "perspectives")
    perspectives: list[PerspectiveDefinition] = []
    seen: set[Perspective] = set()
    for index, raw_perspective in enumerate(perspective_values):
        key = f"perspectives[{index}]"
        entry = _mapping(raw_perspective, key)
        raw_id = _required(entry, f"{key}.id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise _error(f"{key}.id", "must be a non-empty string.")
        try:
            perspective = Perspective(raw_id)
        except ValueError as exc:
            supported = ", ".join(item.value for item in Perspective)
            raise _error(f"{key}.id", f"must be one of: {supported}.") from exc
        if perspective in seen:
            raise _error(f"{key}.id", "is duplicated.")
        seen.add(perspective)
        label = _required(entry, f"{key}.label")
        if not isinstance(label, str) or not label.strip():
            raise _error(f"{key}.label", "must be a non-empty string.")
        question = _required(entry, f"{key}.question")
        if (
            not isinstance(question, str)
            or not question.strip()
            or "\n" in question
            or "\r" in question
        ):
            raise _error(f"{key}.question", "must be a non-empty one-line string.")
        perspectives.append(
            PerspectiveDefinition(id=perspective, label=label, question=question)
        )

    missing = [item.value for item in Perspective if item not in seen]
    if missing:
        raise _error(
            "perspectives",
            f"is missing supported id(s): {', '.join(missing)}.",
        )

    if "prioritise" in statuses:
        raise _error("statuses.prioritise", "was removed and must not be present.")

    working_status = _required(statuses, "statuses.working")
    if not isinstance(working_status, str) or not working_status.strip():
        raise _error("statuses.working", "must be a non-empty string.")

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
        working_status=working_status,
        statuses=checked,
        perspectives=tuple(perspectives),
    )


def clarify_turn_cap() -> int:
    """Return the current maximum number of clarify questions."""
    return load_config().clarify_turn_cap


def status_for(step: InterviewStep) -> str:
    """Return the current package-owned status for an interview step."""
    return load_config().statuses[step]


def working_status() -> str:
    """Return the package-owned general status for active interview work."""
    return load_config().working_status


def opening_question() -> str:
    """Return the package-owned question shown before the first model call."""
    return load_config().opening_question


def interview_client_config() -> InterviewConfig:
    """Return the complete package-owned configuration for a wizard door."""
    current = load_config()
    return InterviewConfig(
        opening_question=current.opening_question,
        working_status=current.working_status,
        perspectives=list(current.perspectives),
    )


__all__ = [
    "CONFIG_FILE",
    "Config",
    "ConfigError",
    "clarify_turn_cap",
    "interview_client_config",
    "load_config",
    "opening_question",
    "status_for",
    "working_status",
]
