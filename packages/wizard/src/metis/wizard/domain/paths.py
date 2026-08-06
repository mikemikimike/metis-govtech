"""Resolving a patch path against the profile tree.

Paths address nodes by id, not by index — `tasks[T-2].behaviours[EB-4].criteria[AC-4.1]`.
Ids rather than positions because a list can be reordered between the model composing a
patch and the applier running it, and an index would then point at the wrong node silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from metis.wizard.domain.profile import ProductProfile

# Bracket contents are opaque. Ids are not supposed to contain a dot — `AC-1-1`, not
# `AC-1.1` — precisely because a dot separates path segments. But ids are written by a model,
# so the scan below walks segment by segment rather than splitting on `.`, and `[^\]]*`
# swallows whatever is inside the brackets whole. A model that ignores the naming rule then
# produces an addressable path rather than a silently mangled one.
_SEGMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[([^\]]*)\])?")


class PathError(Exception):
    """The path is malformed, or names a node that is not there."""


@dataclass(frozen=True)
class Segment:
    field: str
    key: str | None = None  # an id when this segment indexes a list


def parse(path: str) -> list[Segment]:
    segments: list[Segment] = []
    position = 0

    while position < len(path):
        match = _SEGMENT.match(path, position)
        if not match:
            raise PathError(f"Malformed path {path!r} at offset {position}.")
        segments.append(Segment(match.group(1), match.group(2)))
        position = match.end()

        if position < len(path):
            if path[position] != ".":
                raise PathError(f"Malformed path {path!r} at offset {position}.")
            position += 1  # step over the separator
            if position == len(path):
                raise PathError(f"Path {path!r} ends with a separator.")

    if not segments:
        raise PathError(f"Empty path {path!r}.")
    return segments


def _step_into(node: Any, segment: Segment, path: str) -> Any:
    if not hasattr(node, segment.field):
        raise PathError(
            f"{path!r}: no field {segment.field!r} on {type(node).__name__}."
        )
    value = getattr(node, segment.field)

    if segment.key is None:
        return value

    if not isinstance(value, list):
        raise PathError(f"{path!r}: {segment.field!r} is not a list, so it has no ids.")
    for item in value:
        if getattr(item, "id", None) == segment.key:
            return item

    raise PathError(f"{path!r}: no {segment.field[:-1]} with id {segment.key!r}.")


def resolve(profile: ProductProfile, path: str) -> Any:
    """The node a path names."""
    node: Any = profile
    for segment in parse(path):
        node = _step_into(node, segment, path)
    return node


def resolve_parent(profile: ProductProfile, path: str) -> tuple[Any, Segment]:
    """The node *containing* what the path names, plus the final segment.

    What ADD, REMOVE and SET need: to change something you have to hold the thing holding it.
    """
    segments = parse(path)
    node: Any = profile
    for segment in segments[:-1]:
        node = _step_into(node, segment, path)
    return node, segments[-1]
