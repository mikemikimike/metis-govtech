"""Turning the library's universal behaviours into an `Epic`.

The library owns the file; the wizard owns what an epic is. This is the seam between them,
and it is deliberately thin — a dict from over there becomes an `Epic` over here.

Universal behaviours arrive fully formed: statements, criteria, and a metric FQN on each.
Nothing here needs matching, and nothing here is the user's decision.
"""

from __future__ import annotations

from metis.library import universal_epic as _universal_epic_data
from metis.wizard.domain.profile import (
    Behaviour,
    Criterion,
    Epic,
    EpicScope,
    ProductProfile,
)


def universal_epic() -> Epic:
    """The always-on epic, ready to insert into a profile."""
    data = _universal_epic_data()
    return Epic(
        id=data["id"],
        name=data["name"],
        scope=EpicScope.UNIVERSAL,
        behaviours=[
            Behaviour(
                id=b["id"],
                statement=b["statement"],
                # Universals are always measured. `priority` here is not a tick the user
                # made — it is what "always on" means, and `ProductProfile.ticked()`
                # excludes universals precisely so the two never get confused.
                priority=True,
                criteria=[
                    Criterion(
                        id=c["id"],
                        given=c["given"],
                        when=c["when"],
                        then=c["then"],
                        metric_fqn=c["metric_fqn"],
                    )
                    for c in b.get("criteria", [])
                ],
            )
            for b in data.get("behaviours", [])
        ],
    )


def with_universals(profile: ProductProfile) -> ProductProfile:
    """Insert (or replace) the universal epic on a profile, in place.

    Replacing rather than appending matters on resume: a session written before the library
    file was edited would otherwise end up with two EP-UNI epics.
    """
    profile.epics = [e for e in profile.epics if not e.is_universal]
    profile.epics.append(universal_epic())
    return profile
