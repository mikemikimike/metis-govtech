"""
Type definitions for the Langfuse trace extractor.

Contains all TypedDicts and dataclasses used to represent structured data
extracted from Langfuse observations and passed to DeepEval metrics.
"""

from dataclasses import dataclass, field

from typing_extensions import TypedDict

from metis.library.metrics._types import (
    ChatMessage,
    Delegation,
    ObservationSummary,
    PriorTurn,
    ToolCallSummary,
)

__all__ = [
    "ChatMessage",
    "Delegation",
    "ObservationSummary",
    "PriorTurn",
    "RoutingSummary",
    "SessionContext",
    "ToolCallSummary",
]


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




@dataclass
class SessionContext:
    """Session-level context for a trace within a multi-turn conversation."""

    session_id: str
    turn_index: int
    total_turns: int
    prior_turns: list[PriorTurn] = field(default_factory=list)
