"""METIS-side model for Langfuse's v2 observations endpoint.

The v1 `langfuse.api.trace` / `langfuse.api.observations` endpoints 404
permanently once the Langfuse server moves to v4 `events_only` mode. v4 has
no standalone Trace entity: a trace's id/input/output/timestamp live on its
root observation. The root is the observation with `isRootObservation` true
when the server sends that flag (broader than a null parent — it also marks
app roots whose parent span was never exported to Langfuse); when every
observation in a trace has the flag unset (an older server), the root is the
one with no `parentObservationId` instead.

nprd rejects `parse_io_as_json=true` outright (HTTP 400) as of 2026-10-14, so
input/output always arrive as raw strings. This module restores dict/list
typing itself: a string is parsed as JSON only when it looks like an object
or array, and only kept parsed when the result actually is a dict or list —
a plain-text answer like "42" or "true" stays a string.

This module parses the v2 endpoint's camelCase JSON and groups/roots
observations by trace, so the rest of the extractor can keep treating
"trace.input" / "trace.output" / "trace.trace_id" as if a Trace entity still
existed.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

from metis.core.logging import get_logger

logger = get_logger(__name__)


def _maybe_json(value: object) -> object:
    """Parse *value* as JSON only when it looks like an object or array.

    Restores what `parse_io_as_json=true` used to do server-side. A string
    that merely starts with "{" or "[" but fails to parse, or parses into
    something other than a dict/list (e.g. a bare number), is returned
    unchanged — this keeps plain-text answers like "42" or "true" as
    strings instead of silently becoming an int or bool.
    """
    if not isinstance(value, str) or value.lstrip()[:1] not in ("{", "["):
        return value
    try:
        parsed = json.loads(value)
    except ValueError:
        return value
    return parsed if isinstance(parsed, (dict, list)) else value


class ObservationV2(BaseModel):
    """A single observation from `langfuse.api.observations_v_2.get_many`.

    Field names mirror the snake_case attributes the extraction helpers in
    `langfuse.py` already read off the old `ObservationsView` type, so no
    helper needed to change when the fetch layer swapped underneath them.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )

    id: str
    trace_id: str
    session_id: str | None = None
    name: str | None = None
    type: str | None = None
    input: Any = None
    output: Any = None
    metadata: Any = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    parent_observation_id: str | None = None
    is_root_observation: bool | None = None

    @field_validator("input", "output", mode="before")
    @classmethod
    def _parse_io(cls, value: object) -> object:
        return _maybe_json(value)


def group_by_trace(
    observations: list[ObservationV2],
) -> dict[str, list[ObservationV2]]:
    """Group observations by `trace_id`, preserving first-seen trace order."""
    grouped: dict[str, list[ObservationV2]] = {}
    for obs in observations:
        grouped.setdefault(obs.trace_id, []).append(obs)
    return grouped


def select_root(trace_id: str, observations: list[ObservationV2]) -> ObservationV2:
    """Return the root observation for one trace's observation group.

    Prefers `is_root_observation is True`. If every observation in the group
    has `is_root_observation is None` (the server didn't send the flag at
    all), falls back to `parent_observation_id is None` instead. Under
    either method, zero matches (an ingestion gap dropped the root) or
    multiple matches (e.g. a retry re-emitted one) are both logged and
    resolved deterministically by earliest `start_time`, so a single
    malformed trace never crashes the whole evaluation run.
    """
    if any(obs.is_root_observation is not None for obs in observations):
        roots = [obs for obs in observations if obs.is_root_observation]
    else:
        roots = [obs for obs in observations if obs.parent_observation_id is None]

    if len(roots) == 1:
        return roots[0]

    if not roots:
        logger.warning(
            "[langfuse-v2] trace %s has no root observation; "
            "falling back to earliest start_time",
            trace_id,
        )
        candidates = observations
    else:
        logger.warning(
            "[langfuse-v2] trace %s has %d root observations; "
            "falling back to earliest start_time",
            trace_id,
            len(roots),
        )
        candidates = roots

    return min(candidates, key=lambda o: o.start_time or datetime.min)
