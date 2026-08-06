"""Load and compose the package-owned prompts for each model call.

The catalogue is model-facing text. This module owns its validation and substitution, so the
gateway receives a complete value and never needs to know the YAML shape.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from string import Template
from typing import Literal

import yaml

from metis.wizard.application.interview import clarify_turn_cap, opening_question
from metis.wizard.application.interviewer import ClarifyPhase
from metis.wizard.contracts.session_state import Turn
from metis.wizard.domain.profile import ProductProfile

PROMPTS_FILE = "prompts.yaml"
PRIMER_FILE = "agentic-primer.md"

ModelCall = Literal[
    "clarify",
    "behaviours",
    "criteria",
    "personas",
    "scenarios",
    "chat",
    "suggest_criterion",
]

_MODEL_CALL_PLACEHOLDERS: dict[str, frozenset[str]] = {
    "clarify_product": frozenset(
        {"profile", "history", "question_number", "question_cap"}
    ),
    "clarify_machinery": frozenset(
        {"profile", "history", "question_number", "question_cap"}
    ),
    "behaviours": frozenset({"profile", "history"}),
    "criteria": frozenset({"profile"}),
    "personas": frozenset({"profile"}),
    "scenarios": frozenset({"profile"}),
    "chat": frozenset({"profile", "step", "text", "scope"}),
    "suggest_criterion": frozenset({"profile", "behaviour_id"}),
}
_SYSTEM_PLACEHOLDERS = frozenset({"patch_rules", "primer"})


class PromptCatalogError(RuntimeError):
    """The package-owned prompt catalogue cannot be used."""


@dataclass(frozen=True)
class ModelPrompt:
    """One complete, immutable model call composed from one catalogue snapshot."""

    name: ModelCall
    system: str
    user: str


@dataclass(frozen=True)
class PromptCatalog:
    """A complete, validated snapshot of ``prompts.yaml``."""

    system_template: str
    patch_rules: str
    model_calls: Mapping[str, str]


def _error(key: str, detail: str) -> PromptCatalogError:
    return PromptCatalogError(f"{PROMPTS_FILE} key '{key}' {detail}")


def _mapping(value: object, key: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise _error(key, "must be a mapping.")
    return value


def _required(mapping: Mapping[object, object], key: str) -> object:
    name = key.rsplit(".", maxsplit=1)[-1]
    if name not in mapping:
        raise _error(key, "is missing.")
    return mapping[name]


def _text(mapping: Mapping[object, object], key: str) -> str:
    value = _required(mapping, key)
    if not isinstance(value, str) or not value.strip():
        raise _error(key, "must be a non-empty string.")
    return value


def _validate_template(value: str, key: str, allowed: frozenset[str]) -> None:
    template = Template(value)
    if not template.is_valid():
        raise _error(key, "is not a valid $name template.")
    unsupported = sorted(
        identifier
        for identifier in template.get_identifiers()
        if identifier not in allowed
    )
    if unsupported:
        names = ", ".join(unsupported)
        raise _error(key, f"uses unsupported placeholder(s): {names}.")


def _read_catalog_text() -> str:
    try:
        return (
            resources.files("metis.wizard")
            .joinpath(PROMPTS_FILE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise _error("<file>", "is missing.") from exc


def load_prompt_catalog() -> PromptCatalog:
    """Read and validate a fresh prompt-catalogue snapshot."""
    try:
        raw = yaml.safe_load(_read_catalog_text())
    except yaml.YAMLError as exc:
        raise _error("<document>", f"is not valid YAML: {exc}.") from exc

    document = _mapping(raw, "<document>")
    system = _mapping(_required(document, "system"), "system")
    model_calls = _mapping(_required(document, "model_calls"), "model_calls")

    system_template = _text(system, "system.template")
    patch_rules = _text(system, "system.patch_rules")
    _validate_template(system_template, "system.template", _SYSTEM_PLACEHOLDERS)

    calls: dict[str, str] = {}
    for name, allowed in _MODEL_CALL_PLACEHOLDERS.items():
        value = _text(model_calls, f"model_calls.{name}")
        _validate_template(value, f"model_calls.{name}", allowed)
        calls[name] = value

    return PromptCatalog(
        system_template=system_template,
        patch_rules=patch_rules,
        model_calls=calls,
    )


def _substitute(template: str, key: str, values: Mapping[str, str]) -> str:
    try:
        return Template(template).substitute(values)
    except (KeyError, ValueError) as exc:
        missing = exc.args[0] if isinstance(exc, KeyError) else "<template>"
        raise _error(key, f"could not substitute '{missing}'.") from exc


def primer() -> str:
    """Read the agentic background guide without a process-lifetime cache."""
    try:
        return (
            resources.files("metis.wizard.application")
            .joinpath(PRIMER_FILE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise PromptCatalogError(f"{PRIMER_FILE} is missing.") from exc


def _system_message(catalog: PromptCatalog) -> str:
    return _substitute(
        catalog.system_template,
        "system.template",
        {"patch_rules": catalog.patch_rules, "primer": primer()},
    )


def _profile(profile: ProductProfile) -> str:
    return json.dumps(profile.model_dump(mode="json"), indent=2)


def _transcript(history: list[Turn]) -> str:
    return "\n".join(f"{t.role}: {t.text}" for t in history)


def _clarify_position(history: list[Turn]) -> tuple[int, int]:
    """Return the next model question's one-based position and the package cap."""
    asked = sum(1 for turn in history if turn.role == "assistant")
    if (
        history
        and history[0].role == "assistant"
        and history[0].text == opening_question()
    ):
        asked -= 1
    return max(1, asked + 1), clarify_turn_cap()


def _compose(
    template_name: str,
    values: Mapping[str, str],
    *,
    call_name: ModelCall | None = None,
) -> ModelPrompt:
    """Compose system and user messages from one fresh catalogue snapshot."""
    catalog = load_prompt_catalog()
    user = _substitute(
        catalog.model_calls[template_name],
        f"model_calls.{template_name}",
        values,
    )
    return ModelPrompt(
        name=call_name or template_name, system=_system_message(catalog), user=user
    )


def clarify(
    profile: ProductProfile,
    history: list[Turn],
    phase: ClarifyPhase = "product",
) -> ModelPrompt:
    template_name = "clarify_product" if phase == "product" else "clarify_machinery"
    question_number, question_cap = _clarify_position(history)
    return _compose(
        template_name,
        {
            "profile": _profile(profile),
            "history": _transcript(history),
            "question_number": str(question_number),
            "question_cap": str(question_cap),
        },
        call_name="clarify",
    )


def behaviours(profile: ProductProfile, history: list[Turn]) -> ModelPrompt:
    return _compose(
        "behaviours", {"profile": _profile(profile), "history": _transcript(history)}
    )


def criteria(profile: ProductProfile) -> ModelPrompt:
    return _compose("criteria", {"profile": _profile(profile)})


def personas(profile: ProductProfile) -> ModelPrompt:
    return _compose("personas", {"profile": _profile(profile)})


def scenarios(profile: ProductProfile) -> ModelPrompt:
    return _compose("scenarios", {"profile": _profile(profile)})


def chat(
    profile: ProductProfile, step: str, text: str, target: str | None
) -> ModelPrompt:
    scope = f"\nThey are talking about {target}." if target else ""
    return _compose(
        "chat",
        {
            "profile": _profile(profile),
            "step": step,
            "text": text,
            "scope": scope,
        },
    )


def suggest_criterion(profile: ProductProfile, behaviour_id: str) -> ModelPrompt:
    return _compose(
        "suggest_criterion",
        {"profile": _profile(profile), "behaviour_id": behaviour_id},
    )


__all__ = [
    "ModelCall",
    "ModelPrompt",
    "ClarifyPhase",
    "PROMPTS_FILE",
    "PRIMER_FILE",
    "PromptCatalog",
    "PromptCatalogError",
    "behaviours",
    "chat",
    "clarify",
    "criteria",
    "load_prompt_catalog",
    "personas",
    "primer",
    "scenarios",
    "suggest_criterion",
]
