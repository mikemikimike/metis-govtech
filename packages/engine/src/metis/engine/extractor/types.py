"""
Type definitions for the Langfuse trace extractor.

Contains all TypedDicts and dataclasses used to represent structured data
extracted from Langfuse observations and passed to DeepEval metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NotRequired

from typing_extensions import TypedDict


class RoutingSummary(TypedDict):
    """Aggregate routing statistics for an evaluation run.

    Summarises how traces were classified and routed to subagents
    during the three-phase evaluation pipeline.

    TypedDict rather than dataclass because this is serialized directly
    to JSON via :func:`json.dumps` in :mod:`report` and consumed
    with ``["key"]`` access throughout the report rendering code.
    """

    total_traces: int
    total_sessions: int
    direct_handle: int
    routing_failed: int
    subagent_counts: dict


class SessionToolCallData(TypedDict):
    """Shape of a tool-call entry inside :class:`SessionTurnData`.

    TypedDict rather than dataclass because these are serialized directly to
    JSON via :func:`json.dumps` in :mod:`report` and consumed with
    ``["key"]`` access throughout the report rendering code.
    """

    name: str
    input: str
    output: str


class SessionTurnData(TypedDict):
    """Shape of a single turn entry inside :class:`SessionMetricsEntry`.

    TypedDict rather than dataclass because these are serialized directly to
    JSON and consumed with ``["key"]`` access in :mod:`report`.
    """

    role: str
    content: str
    tools: NotRequired[list]


class SessionMetricResult(TypedDict):
    """Shape of a single metric result inside :class:`SessionMetricsEntry`.

    TypedDict rather than dataclass because these are serialized directly to
    JSON and consumed with ``["key"]`` access in :mod:`report`.
    """

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool


class SessionMetricsEntry(TypedDict):
    """Shape of one session's metrics data passed to
    :func:`report_from_evaluate_result`.

    TypedDict rather than dataclass because the report layer serializes these
    with :func:`json.dumps` (no ``dataclasses.asdict`` needed) and reads fields
    with dict subscript access throughout :mod:`report`.
    """

    session_id: str
    num_turns: int
    turns: list
    metrics: list


class PriorTurn(TypedDict):
    """A summarised prior conversation turn for session context."""

    input: str
    output: str
    routed_to: str


class Delegation(TypedDict):
    """A subagent delegation extracted from trace observations."""

    target: str
    task: str


class ChatMessage(TypedDict):
    """A chat message with role and content."""

    role: str
    content: str


class ObservationSummary(TypedDict):
    """Serialised subset of a Langfuse observation carried in TraceMetadata."""

    id: str
    name: str | None
    type: str | None
    input: Any
    output: Any
    metadata: Any
    start_time: datetime | None
    end_time: datetime | None
    parent_observation_id: str | None


class ToolCallSummary(TypedDict):
    """Serialised subset of a TOOL observation carried in TraceMetadata."""

    name: str | None
    type: str | None
    input: Any
    output: Any


@dataclass
class SessionContext:
    """Session-level context for a trace within a multi-turn conversation."""

    session_id: str
    turn_index: int
    total_turns: int
    prior_turns: list[PriorTurn] = field(default_factory=list)
