"""What the model may write, and where.

Two pieces of **config, not models**, because a patch can reach a field two different ways and
an address check only sees one of them.

`StepPermissions` maps a step to the path globs it owns. Two rules make it work, and both are
structural rather than prompt instructions:

**The check is against the step that owns the address, not the step you are standing in.**
Asking to reword EB-4 while sitting at the criteria step should simply work: the behaviours
step owns behaviour statements, so the patch is applied where you stand and your current step
never changes. Being told to press Back first would be the wizard enforcing its own structure
over a clearly stated intent. It stays bounded — an address no step owns is writable nowhere.

**Some addresses are unwritable by the model at any step.** `priority` is the user's only real
decision, and `num_trials` and `fixtures` are the user's to set, so none of them appears in any
entry.

Bundled model values are protected at the structured-output boundary: strict draft models reject
persisted ids, defaults, authorship and matcher-owned fields before a domain object exists.
"""

from __future__ import annotations

import re
from enum import StrEnum


class SessionStep(StrEnum):
    CLARIFY = "clarify"
    BEHAVIOURS = "behaviours"
    PRIORITISE = "prioritise"
    CRITERIA = "criteria"
    PERSONAS = "personas"
    TASKS = "tasks"
    DONE = "done"


# Note that CLARIFY and PRIORITISE have no entry, which is the point. Both steps exist and
# the model may write nothing during either: clarify commits nothing at all, and the ticks
# that make prioritise work are PatchOrigin.WIZARD, so they never reach an address check.
# Note that each step owns both the *container* and its *elements*. ADD addresses the list
# it appends to (`epics`, `epics[EP-1].behaviours`), while SET and REMOVE address an element
# (`epics[EP-1]`). Listing only one of the two silently forbids half the operations.
StepPermissions: dict[SessionStep, list[str]] = {
    SessionStep.BEHAVIOURS: [
        "epics",
        "epics[*]",
        "epics[*].name",
        "epics[*].behaviours",
        "epics[*].behaviours[*]",
        "epics[*].behaviours[*].statement",
        "product.summary",
        "product.users",
        "product.architecture",
        "product.name",
    ],
    SessionStep.CRITERIA: [
        "epics[*].behaviours[*].criteria",
        "epics[*].behaviours[*].criteria[*]",
        "epics[*].behaviours[*].criteria[*].given",
        "epics[*].behaviours[*].criteria[*].when",
        "epics[*].behaviours[*].criteria[*].then",
    ],
    SessionStep.PERSONAS: [
        "personas",
        "personas[*]",
        "personas[*].description",
    ],
    SessionStep.TASKS: [
        "tasks",
        "tasks[*]",
        "tasks[*].description",
        "tasks[*].behaviour_refs",
        "tasks[*].persona_refs",
    ],
}


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """`epics[*].behaviours[*]` matches `epics[EP-1].behaviours[EB-4]`.

    `*` stands for one id inside brackets and never spans a `.`, so a glob for a behaviour
    cannot accidentally match something nested deeper under it.
    """
    parts = []
    for token in re.split(r"(\[\*\])", glob):
        if token == "[*]":
            parts.append(r"\[[^\]]+\]")
        else:
            parts.append(re.escape(token))
    return re.compile("^" + "".join(parts) + "$")


_COMPILED: dict[SessionStep, list[re.Pattern[str]]] = {
    step: [_glob_to_regex(g) for g in globs] for step, globs in StepPermissions.items()
}


def owner_of(path: str) -> SessionStep | None:
    """Which step owns this address, if any.

    Deliberately not "may my current step write this?". A path owned by no step is writable
    at no point, ever — which is what bounds the whole arrangement.
    """
    for step, patterns in _COMPILED.items():
        if any(p.match(path) for p in patterns):
            return step
    return None
