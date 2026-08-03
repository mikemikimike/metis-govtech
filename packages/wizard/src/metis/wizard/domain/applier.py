"""Applying patches to the profile.

The order of the checks is the whole design:

    1. origin      — did the package compose this? then it is trusted
    2. universal    — is it under EP-UNI? then no, from anyone, at any step
    3. ownership    — does *any* step own this address?

Origin comes first because an address check alone cannot tell the user's tick from the
model's attempt at one — the two patches are byte-identical. See `PatchOrigin`.

A rejected patch is never silent. The user asked for something and part of it did not happen,
so the applier says which part and why, and the caller attaches that as a RUNTIME warning.
Attribution matters more here than anywhere else: it is the one message where the wizard has
to say *I chose not to*, rather than *you did something wrong* or *something broke*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from metis.wizard.domain import paths
from metis.wizard.domain.patch import Patch, PatchOp, PatchOrigin
from metis.wizard.domain.permissions import owner_of
from metis.wizard.domain.profile import (
    Behaviour,
    Criterion,
    Epic,
    Persona,
    ProductProfile,
    Task,
)

# What a list of each name holds, so an ADD patch can build the right object from a dict.
_LIST_TYPES: dict[str, type] = {
    "epics": Epic,
    "behaviours": Behaviour,
    "criteria": Criterion,
    "personas": Persona,
    "tasks": Task,
}


@dataclass
class Rejection:
    """One patch that did not happen, and the sentence the user is shown."""

    patch: Patch
    reason: str

    @property
    def message(self) -> str:
        return self.reason


class PatchValueError(Exception):
    """A model patch carries data that cannot build the node at its destination."""


@dataclass
class ApplyResult:
    applied: list[Patch] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)

    @property
    def any_rejected(self) -> bool:
        return bool(self.rejected)


def _check(profile: ProductProfile, patch: Patch) -> str | None:
    """Return a rejection reason, or None if the patch may be applied."""
    # 1. Universals are read-only to *everyone*, at every step, whoever composed the patch.
    #    This is checked before origin rather than after: the package never composes a patch
    #    under EP-UNI, so trusting WIZARD origin here would only ever wave through a bug.
    #    Enforced here rather than by omission from StepPermissions so that a new step
    #    cannot accidentally gain access to it.
    try:
        if paths.owning_epic_scope(profile, patch.path) == "universal":
            return (
                "Those are the checks that always run, so they're not mine to change — "
                "or yours. Everything else on this screen is still up for discussion."
            )
    except paths.PathError:
        pass  # a malformed path is caught by the ownership check below

    # 2. The package composed it, and knows it did, at the moment it drew the option.
    if patch.origin is PatchOrigin.WIZARD:
        return None

    # 3. Not "does my current step allow this?" but "does any step own it?".
    if owner_of(patch.path) is None:
        if patch.path.endswith(".priority"):
            return (
                "I've made that change. I can't tick it for you, though — "
                "which behaviours actually matter is your call, not mine."
            )
        if patch.path.endswith(".metric_fqn"):
            # Metrics are chosen by the matcher from the criterion's wording, never written
            # directly. The model is told to reword instead; if one slips through anyway, the
            # user hears about the wording, not a field they have never seen.
            return (
                "The metric is chosen from how the criterion is worded, so I can't set it "
                "directly — but rewording the criterion will point it at the right one."
            )
        # A model patch for an address no step owns. The path is package bookkeeping the user
        # has never seen, so it is named as "part of this" rather than shown verbatim.
        return "I wasn't able to make part of that change — it isn't mine to write."

    return None


def _coerce(field_name: str, value: Any) -> Any:
    """Turn a dict from model output into the object its list holds."""
    model = _LIST_TYPES.get(field_name)
    if model is not None and isinstance(value, dict):
        return model.model_validate(value)
    return value


def _apply_one(profile: ProductProfile, patch: Patch) -> None:
    parent, segment = paths.resolve_parent(profile, patch.path)

    if patch.op is PatchOp.SET:
        if segment.key is None:
            setattr(parent, segment.field, _coerce(segment.field, patch.value))
        else:
            # Replacing a whole element by id, e.g. SET epics[EP-1].behaviours[EB-4].
            items = getattr(parent, segment.field)
            replacement = _coerce(segment.field, patch.value)
            for i, item in enumerate(items):
                if getattr(item, "id", None) == segment.key:
                    items[i] = replacement
                    return
            raise paths.PathError(f"{patch.path!r}: nothing with id {segment.key!r}.")

    elif patch.op is PatchOp.ADD:
        items = getattr(parent, segment.field)
        if not isinstance(items, list):
            raise paths.PathError(f"{patch.path!r}: cannot ADD to a non-list.")
        items.append(_coerce(segment.field, patch.value))

    elif patch.op is PatchOp.REMOVE:
        items = getattr(parent, segment.field)
        if segment.key is None:
            raise paths.PathError(f"{patch.path!r}: REMOVE needs an id.")
        remaining = [i for i in items if getattr(i, "id", None) != segment.key]
        if len(remaining) == len(items):
            raise paths.PathError(f"{patch.path!r}: nothing with id {segment.key!r}.")
        setattr(parent, segment.field, remaining)

    elif patch.op is PatchOp.REORDER:
        items = getattr(parent, segment.field)
        order = {id_: i for i, id_ in enumerate(patch.value or [])}
        setattr(
            parent,
            segment.field,
            sorted(items, key=lambda x: order.get(getattr(x, "id", None), len(order))),
        )


def apply(profile: ProductProfile, patches: list[Patch]) -> ApplyResult:
    """Apply what is allowed, report what was not.

    Patches are applied in order. Nothing here guards against a *set* of patches that
    conflict — that case is removed a level up instead: anything the user can click together
    is guaranteed not to conflict (see `multi`), and suggestion chips are one at a time.
    """
    result = ApplyResult()

    for patch in patches:
        reason = _check(profile, patch)
        if reason is not None:
            result.rejected.append(Rejection(patch, reason))
            continue
        try:
            _apply_one(profile, patch)
        except paths.PathError as exc:
            result.rejected.append(Rejection(patch, f"I couldn't apply that: {exc}"))
            continue
        except ValidationError:
            # The value won't build the object its list holds — a bad enum, or a nested
            # field the wrong shape. `Patch.value` is `Any`, so this is the first point the
            # shape is checked; a malformed value must be a rejected patch, never a crash
            # partway through an interview.
            result.rejected.append(
                Rejection(patch, f"I couldn't apply that change to {patch.path}.")
            )
            continue
        result.applied.append(patch)

    return result


def sanitise(patches: Sequence[Patch]) -> list[Patch]:
    """Force every patch to MODEL origin.

    Call this on anything that came out of a model. Origin is stamped by the code that builds
    a patch and is never carried in structured output, so a model claiming `wizard` is either
    confused or trying it on; either way the answer is the same.
    """
    return [p.model_copy(update={"origin": PatchOrigin.MODEL}) for p in patches]


def validate_model_patches(profile: ProductProfile, patches: Sequence[Patch]) -> None:
    """Validate model patch values without touching the real profile.

    `Patch.value` is necessarily `Any`: its shape depends on the path. Structured output
    therefore validates only the patch envelope. Applying to a deep copy closes that gap and
    lets the gateway feed a domain validation error back through its normal retry loop.

    Policy and path rejections remain the applier's concern. They describe something the
    wizard refuses or cannot locate, not malformed structured output.
    """
    candidate = profile.model_copy(deep=True)
    previous_persona_counts = _persona_description_counts(profile)

    for patch in sanitise(patches):
        if _check(candidate, patch) is not None:
            continue
        try:
            _apply_one(candidate, patch)
            # Assignment itself is not validated on Pydantic models. Rebuilding after every
            # patch catches scalar SETs and list-shaped values as well as nested model errors.
            candidate = ProductProfile.model_validate(
                candidate.model_dump(mode="python", warnings=False)
            )
        except paths.PathError:
            continue
        except (ValidationError, TypeError, AttributeError) as exc:
            raise PatchValueError(
                f"The patch at {patch.path!r} has a value that does not fit there:\n{exc}"
            ) from exc

    # A model should update or remove an existing persona, not append the same prose under
    # another id. Check after the whole patch set so a legitimate add-then-remove replacement
    # is judged in its final state rather than halfway through.
    duplicate = next(
        (
            (description, ids)
            for description, ids in _persona_descriptions(candidate).items()
            if len(ids) > max(1, previous_persona_counts.get(description, 0))
        ),
        None,
    )
    if duplicate:
        _, ids = duplicate
        raise PatchValueError(
            "The proposed patches duplicate one persona description under "
            f"{', '.join(ids)}. Update or remove the existing persona instead of adding "
            "the same content again."
        )


def _normalise_prose(value: str) -> str:
    return " ".join(value.split()).casefold()


def _persona_descriptions(profile: ProductProfile) -> dict[str, list[str]]:
    descriptions: dict[str, list[str]] = {}
    for persona in profile.personas:
        descriptions.setdefault(_normalise_prose(persona.description), []).append(
            persona.id
        )
    return descriptions


def _persona_description_counts(profile: ProductProfile) -> dict[str, int]:
    return {
        description: len(ids)
        for description, ids in _persona_descriptions(profile).items()
    }
