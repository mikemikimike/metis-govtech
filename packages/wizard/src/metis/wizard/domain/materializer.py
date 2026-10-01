"""Application-owned construction of persisted profile entities."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from metis.wizard.domain.documents import (
    fixture_name_identity,
    normalize_fixture_name,
)
from metis.wizard.domain.patch import PatchOrigin
from metis.wizard.domain.profile import (
    Behaviour,
    Criterion,
    CriterionDescription,
    Feature,
    Persona,
    ProductProfile,
    Scenario,
)


def _next_numeric(ids: set[str], prefix: str) -> str:
    numbers = [
        int(match.group(1))
        for value in ids
        if (match := re.fullmatch(re.escape(prefix) + r"-(\d+)", value))
    ]
    return f"{prefix}-{max(numbers, default=0) + 1}"


def _slug(name: str) -> str:
    value = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "persona"


def _persona_id(issued_ids: set[str], name: str, *, manual: bool) -> str:
    if manual:
        return _next_numeric(issued_ids, "P")
    base = _slug(name)
    candidate = base
    suffix = 2
    while candidate in issued_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _record(
    issued_ids: set[str], user_typed: set[str] | None, node_id: str, origin: PatchOrigin
) -> None:
    """Record identity before the caller inserts the node into the profile."""
    issued_ids.add(node_id)
    if origin is PatchOrigin.WIZARD and user_typed is not None:
        user_typed.add(node_id)


def add_feature(
    profile: ProductProfile,
    draft: Any,
    origin: PatchOrigin,
    *,
    issued_ids: set[str],
    user_typed: set[str] | None = None,
) -> Feature:
    feature = Feature(
        id=_next_numeric(issued_ids, "F"),
        name=draft.name,
        description=draft.description,
        behaviours=[],
    )
    _record(issued_ids, user_typed, feature.id, origin)
    for behaviour_draft in draft.behaviours:
        feature.behaviours.append(
            add_behaviour(
                profile,
                behaviour_draft,
                origin,
                issued_ids=issued_ids,
                user_typed=user_typed,
            )
        )
    profile.features.append(feature)
    return feature


def add_behaviour(
    profile: ProductProfile,
    draft: Any,
    origin: PatchOrigin,
    *,
    issued_ids: set[str],
    user_typed: set[str] | None = None,
) -> Behaviour:
    behaviour = Behaviour(
        id=_next_numeric(issued_ids | {b.id for b in profile.behaviours()}, "EB"),
        name=draft.name,
        description=draft.description,
        measured=True,
    )
    _record(issued_ids, user_typed, behaviour.id, origin)
    return behaviour


def add_criterion(
    profile: ProductProfile,
    behaviour: Behaviour,
    draft: Any,
    origin: PatchOrigin,
    *,
    issued_ids: set[str],
    user_typed: set[str] | None = None,
) -> Criterion:
    # Criterion ids keep the parent number, so this assumes a Behaviour id ends in a number.
    number = re.search(r"(\d+)$", behaviour.id)
    stem = number.group(1) if number else behaviour.id
    prefix = f"AC-{stem}"
    criterion = Criterion(
        id=_next_numeric(issued_ids, prefix),
        name=draft.name,
        description=CriterionDescription(
            given=draft.given,
            when=draft.when,
            then=draft.then,
        ),
    )
    _record(issued_ids, user_typed, criterion.id, origin)
    behaviour.criteria.append(criterion)
    return criterion


def add_persona(
    profile: ProductProfile,
    draft: Any,
    origin: PatchOrigin,
    *,
    issued_ids: set[str],
    user_typed: set[str] | None = None,
) -> Persona:
    persona = Persona(
        id=_persona_id(issued_ids, draft.name, manual=origin is PatchOrigin.WIZARD),
        name=draft.name,
        description=draft.description,
    )
    _record(issued_ids, user_typed, persona.id, origin)
    profile.personas.append(persona)
    return persona


def add_scenario(
    profile: ProductProfile,
    draft: Any,
    origin: PatchOrigin,
    *,
    issued_ids: set[str],
    user_typed: set[str] | None = None,
    allowed_fixture_names: set[str] | None = None,
) -> Scenario:
    behaviour_ids = {b.id for b in profile.behaviours()}
    persona_ids = {p.id for p in profile.personas}
    unknown_behaviours = set(draft.behaviour_refs) - behaviour_ids
    unknown_personas = set(draft.persona_refs) - persona_ids
    if unknown_behaviours or unknown_personas:
        missing = sorted(unknown_behaviours | unknown_personas)
        raise ValueError(f"scenario references unknown ids: {', '.join(missing)}")
    available = {
        fixture_name_identity(name): normalize_fixture_name(name)
        for name in (allowed_fixture_names or set())
    }
    fixtures: list[str] = []
    seen_fixtures: set[str] = set()
    if origin is not PatchOrigin.MODEL and draft.fixtures:
        raise ValueError("Only a model Scenario draft can suggest fixtures.")
    for raw_name in draft.fixtures:
        name = normalize_fixture_name(raw_name)
        if name != raw_name:
            raise ValueError("scenario fixture names must already be normalized")
        identity = fixture_name_identity(name)
        if identity in seen_fixtures:
            raise ValueError(f"scenario fixture '{name}' is duplicated")
        if identity not in available:
            raise ValueError(f"scenario fixture '{name}' is not available")
        seen_fixtures.add(identity)
        fixtures.append(available[identity])
    scenario = Scenario(
        id=_next_numeric(issued_ids, "S"),
        name=draft.name,
        description=draft.description,
        behaviour_refs=list(draft.behaviour_refs),
        persona_refs=list(draft.persona_refs),
        fixtures=fixtures,
        num_trials=3,
    )
    _record(issued_ids, user_typed, scenario.id, origin)
    profile.scenarios.append(scenario)
    return scenario
