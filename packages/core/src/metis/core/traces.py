"""What a grader reads: the Langfuse traces of one session.

METIS supports Langfuse v4 only. In v4 a trace is not stored as an object of its own: it is the
set of observations sharing a ``traceId``, and its input and output are those of its logical
root observation. ``Observation`` is one row of Observations API v2, ``Trace`` is the group METIS
builds from those rows, and ``GradingInput`` is the whole session plus the artifacts the run
produced.

These live in ``metis-core`` because the engine, the trace cache and ``metis-insights`` all read
them, and ``insights`` may depend only on ``core``. Holding Langfuse's SDK type instead would make
``core`` depend on ``langfuse``.

Every model here is frozen and every collection is a tuple, because one ``GradingInput`` is
shared by every grader run on a session, and those runs execute concurrently. A grader that
tries to reassign or reorder its input fails on its own line. ``input``/``output``/``metadata``
are ``Any`` and usually hold parsed dicts, which freezing does not protect, so graders must
treat them as read-only too.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from metis.core.artifacts import Artifact
from metis.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = get_logger(__name__)


def _maybe_json(value: object) -> object:
    """Parse *value* as JSON only when it looks like an object or array.

    Langfuse rejects ``parse_io_as_json`` on the v2 endpoint and returns input/output as raw
    strings. A string is parsed only when it starts with ``{`` or ``[``, and the parse is kept
    only if it produced a dict or list, so a plain-text answer like ``"42"`` or ``"true"`` stays
    a string.
    """
    if not isinstance(value, str) or value.lstrip()[:1] not in ("{", "["):
        return value
    try:
        parsed = json.loads(value)
    except ValueError:
        return value
    return parsed if isinstance(parsed, (dict, list)) else value


class Observation(BaseModel):
    """One Langfuse observation, as returned by Observations API v2.

    Holds the subset of Observations API v2 fields that graders read, under the same names.
    Fields METIS does not use are dropped on validation. A raw API row validates directly: its
    camelCase keys (``traceId``) map onto the snake_case fields, and every field except the two
    ids may be missing. A field is ``None`` both when it is empty and when its field group was
    not requested, so the fetch requests every group these fields come from.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore", frozen=True
    )

    id: str
    trace_id: str
    session_id: str | None = None
    parent_observation_id: str | None = None
    is_root_observation: bool | None = None
    """Langfuse's logical-root flag; see ``Trace.root``. May be absent on every observation in a
    trace at once."""
    type: str | None = None
    """E.g. ``"SPAN"``, ``"GENERATION"``, ``"TOOL"``. A ``str``, not a ``Literal``: Langfuse has
    added observation types before, and a ``Literal`` would reject every observation of a type
    METIS does not know yet."""
    name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    input: Any = None
    """A JSON object or array string is parsed; see ``_maybe_json``."""
    output: Any = None
    """Parsed the same way as ``input``."""
    metadata: Any = None
    """Fetched with ``expandMetadata``, so never truncated."""

    @field_validator("input", "output", mode="before")
    @classmethod
    def _parse_io(cls, value: object) -> object:
        return _maybe_json(value)


def _oldest_first(observation: Observation) -> tuple[bool, float]:
    """Sort key for storage order: by ``start_time``, missing times last.

    The placeholder ``0.0`` keeps the key comparable when two observations both lack a time;
    ``sorted`` is stable, so those keep their relative order.
    """
    start = observation.start_time
    return (start is None, start.timestamp() if start else 0.0)


def _earliest_with_missing_first(observation: Observation) -> tuple[bool, float]:
    """Tie-break key for ``Trace.root``: a missing ``start_time`` counts as earliest."""
    start = observation.start_time
    return (start is not None, start.timestamp() if start else 0.0)


class Trace(BaseModel, frozen=True):
    """One exchange between persona and target.

    ``Trace`` has no ``input``/``output`` of its own. Langfuse's default is that a trace's input
    and output are the root observation's, but an application can override that per trace, so a
    grader reads them from whichever observation it considers authoritative, which is usually
    ``trace.root.input`` / ``trace.root.output``.
    """

    id: str
    """The Langfuse ``traceId`` shared by every observation in ``observations``."""

    session_id: str
    """The Langfuse ``sessionId``; every trace of one simulated conversation shares it."""

    observations: tuple[Observation, ...] = Field(min_length=1)
    """Every observation with this ``traceId``, oldest first by ``start_time``, with any
    observation lacking a ``start_time`` last. Never empty, since a trace is only known through
    one of its observations."""

    @field_validator("observations")
    @classmethod
    def _sort_oldest_first(
        cls, observations: tuple[Observation, ...]
    ) -> tuple[Observation, ...]:
        return tuple(sorted(observations, key=_oldest_first))

    @classmethod
    def from_observations(
        cls, trace_id: str, session_id: str, observations: Iterable[Observation]
    ) -> Trace:
        """Build a trace from one ``traceId``'s rows, in any order."""
        return cls(id=trace_id, session_id=session_id, observations=tuple(observations))

    @cached_property
    def root(self) -> Observation:
        """The observation Langfuse marks as this trace's logical root.

        Found by ``is_root_observation`` when any observation in the trace has it set. If no
        observation has it set, falls back to the observation with no
        ``parent_observation_id``. The flag can mean an SDK-detected "app root" rather than a
        parentless span, so the fallback applies only when the flag is absent from the whole
        trace, not when it is merely false.

        Zero or several candidates under either rule (an ingestion gap, or a retry that
        re-emitted a root) resolve to the earliest ``start_time``, with a missing time counted
        as earliest, and a warning logged. This does not raise, so one malformed trace cannot
        crash an evaluation run.
        """
        observations = self.observations
        if any(o.is_root_observation is not None for o in observations):
            candidates = [o for o in observations if o.is_root_observation]
        else:
            candidates = [o for o in observations if o.parent_observation_id is None]

        if len(candidates) == 1:
            return candidates[0]

        logger.warning(
            "[traces] trace %s has %d root candidates; falling back to earliest start_time",
            self.id,
            len(candidates),
        )
        return min(candidates or observations, key=_earliest_with_missing_first)


class GradingInput(BaseModel, frozen=True):
    """Everything one grader run sees: the whole session and the run's artifacts."""

    traces: tuple[Trace, ...]
    """The whole session, in order, including traces whose root has no output (the target
    crashed or timed out mid-answer). A grader that needs an output skips those itself."""

    artifacts: tuple[Artifact, ...] = ()
    """Every artifact the run produced, with ``path`` already resolved to a local file path.
    ``()`` when the run produced none. Not tied to individual traces (see issue #428, "Open
    questions and known gaps")."""
