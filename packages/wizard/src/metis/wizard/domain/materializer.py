"""Application-owned construction of persisted profile entities."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from metis.wizard.domain.patch import PatchOrigin
from metis.wizard.domain.profile import (
    Behaviour,
    Criterion,
    InteractionType,
    Persona,
    ProductProfile,
    Scenario,
    Task,
)


def _next_numeric(ids: set[str], prefix: str) -> str:
    numbers = [
        int(match.group(1))
        for value in ids
        if (match := re.fullmatch(re.escape(prefix) + r"-(\d+)", value))
    ]
    return f"{prefix}-{max(numbers, default=0) + 1}"


def _slug(label: str) -> str:
    value = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "persona"


def _persona_id(profile: ProductProfile, label: str, *, manual: bool) -> str:
    used = {p.id for p in profile.personas}
    used.update(ref for scenario in profile.scenarios for ref in scenario.persona_refs)
    if manual:
        return _next_numeric(used, "P")
    base = _slug(label)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _interaction(origin: PatchOrigin) -> InteractionType:
    return (
        InteractionType.FORM if origin is PatchOrigin.WIZARD else InteractionType.CHAT
    )


def add_task(profile: ProductProfile, draft: Any, origin: PatchOrigin) -> Task:
    task = Task(
        id=_next_numeric({t.id for t in profile.tasks}, "T"),
        name=draft.name,
        behaviours=[],
    )
    profile.tasks.append(task)
    for behaviour_draft in draft.behaviours:
        task.behaviours.append(
            add_behaviour(profile, behaviour_draft, origin, task=task)
        )
    return task


def add_behaviour(
    profile: ProductProfile,
    draft: Any,
    origin: PatchOrigin,
    *,
    task: Task | None = None,
) -> Behaviour:
    behaviour = Behaviour(
        id=_next_numeric({b.id for b in profile.behaviours()}, "EB"),
        statement=draft.statement,
        interaction_type=_interaction(origin),
    )
    if task is not None:
        # The caller appends the returned object; accepting ``task`` here keeps the ownership
        # explicit while avoiding a second append.
        pass
    return behaviour


def add_criterion(
    profile: ProductProfile, behaviour: Behaviour, draft: Any, origin: PatchOrigin
) -> Criterion:
    used = {
        criterion.id for item in profile.behaviours() for criterion in item.criteria
    }
    number = re.search(r"(\d+)$", behaviour.id)
    stem = number.group(1) if number else behaviour.id
    prefix = f"AC-{stem}"
    criterion = Criterion(
        id=_next_numeric(used, prefix),
        given=draft.given,
        when=draft.when,
        then=draft.then,
        interaction_type=_interaction(origin),
    )
    behaviour.criteria.append(criterion)
    return criterion


def add_persona(profile: ProductProfile, draft: Any, origin: PatchOrigin) -> Persona:
    persona = Persona(
        id=_persona_id(profile, draft.label, manual=origin is PatchOrigin.WIZARD),
        description=draft.description,
        interaction_type=_interaction(origin),
    )
    profile.personas.append(persona)
    return persona


def add_scenario(profile: ProductProfile, draft: Any, origin: PatchOrigin) -> Scenario:
    behaviour_ids = {b.id for b in profile.behaviours()}
    persona_ids = {p.id for p in profile.personas}
    unknown_behaviours = set(draft.behaviour_refs) - behaviour_ids
    unknown_personas = set(draft.persona_refs) - persona_ids
    if unknown_behaviours or unknown_personas:
        missing = sorted(unknown_behaviours | unknown_personas)
        raise ValueError(f"scenario references unknown ids: {', '.join(missing)}")
    scenario = Scenario(
        id=_next_numeric({s.id for s in profile.scenarios}, "S"),
        description=draft.description,
        behaviour_refs=list(draft.behaviour_refs),
        persona_refs=list(draft.persona_refs),
        fixtures=[],
        num_trials=3,
        interaction_type=_interaction(origin),
    )
    profile.scenarios.append(scenario)
    return scenario
