"""Transport-neutral impact rules for edits to a wizard profile.

This module deliberately knows nothing about screens, requests, or terminal/web UI.  It
answers the domain question: which derived nodes are affected by a set of edits, and what
derived state can be discarded when a user asks for regeneration?
"""

from __future__ import annotations

from dataclasses import dataclass

from metis.wizard.domain.patch import Patch
from metis.wizard.domain.profile import ProductProfile

BEHAVIOUR_STATEMENT = "statement"
PRODUCT_WIDE = ("product.summary", "product.architecture")


@dataclass(frozen=True)
class Impact:
    """A derived profile node whose current value may need a user decision."""

    subject: str
    kind: str  # "criteria" | "scenario" | "tree"
    related_to: str | None = None


def impacts_for(profile: ProductProfile, patches: list[Patch]) -> list[Impact]:
    """Return derived nodes affected by ``patches``, in user-facing order."""
    impacts: list[Impact] = []
    seen: set[tuple[str, str]] = set()

    for patch in patches:
        path = patch.path

        if path in PRODUCT_WIDE:
            has_derived_work = bool(profile.tasks) or bool(profile.scenarios)
            if not has_derived_work:
                continue
            key = ("tree", "product")
            if key not in seen:
                seen.add(key)
                impacts.append(Impact(subject=path, kind="tree"))
            continue

        if not path.endswith(f".{BEHAVIOUR_STATEMENT}"):
            continue

        behaviour_id = _behaviour_id(path)
        behaviour = profile.behaviour(behaviour_id) if behaviour_id else None
        if behaviour is None:
            continue

        if behaviour.criteria and ("criteria", behaviour.id) not in seen:
            seen.add(("criteria", behaviour.id))
            impacts.append(Impact(subject=behaviour.id, kind="criteria"))

        for scenario in profile.scenarios_covering(behaviour.id):
            if ("scenario", scenario.id) in seen:
                continue
            seen.add(("scenario", scenario.id))
            impacts.append(
                Impact(subject=scenario.id, kind="scenario", related_to=behaviour.id)
            )

    return impacts


def clear_for_regeneration(profile: ProductProfile, impact: Impact) -> None:
    """Discard only model-derived state represented by ``impact``."""
    if impact.kind == "criteria":
        behaviour = profile.behaviour(impact.subject)
        if behaviour is not None:
            behaviour.criteria = [c for c in behaviour.criteria if c.is_user_typed]

    elif impact.kind == "scenario":
        scenario = profile.scenario(impact.subject)
        if scenario is not None and not scenario.is_user_typed:
            profile.scenarios = [s for s in profile.scenarios if s.id != impact.subject]

    elif impact.kind == "tree":
        profile.tasks = []
        profile.scenarios = []


def _behaviour_id(path: str) -> str | None:
    """Extract ``EB-*`` from ``tasks[T-1].behaviours[EB-4].statement``."""
    marker = "behaviours["
    if marker not in path:
        return None
    return path.split(marker, 1)[1].split("]", 1)[0]
