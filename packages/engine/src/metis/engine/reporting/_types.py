"""TypedDicts for the report-ready data format.

These represent the serializable shape of evaluation results after conversion
from the structured dataclass types (TurnResult, SessionResult) into the
dict-based format consumed by report renderers and written to JSON/HTML.
"""

from __future__ import annotations

from typing import NotRequired

from typing_extensions import TypedDict


class SessionToolCallData(TypedDict):
    """Shape of a tool-call entry inside :class:`SessionTurnData`."""

    name: str
    input: str
    output: str


class SessionTurnData(TypedDict):
    """Shape of a single turn entry inside :class:`SessionMetricsEntry`."""

    role: str
    content: str
    tools: NotRequired[list[SessionToolCallData]]


class SessionMetricResult(TypedDict):
    """Shape of a single metric result inside :class:`SessionMetricsEntry`."""

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool


class SessionMetricsEntry(TypedDict):
    """Shape of one session's report-ready metrics data."""

    session_id: str
    num_turns: int
    turns: list[SessionTurnData]
    metrics: list[SessionMetricResult]


class TurnMetricResult(TypedDict, total=False):
    """Shape of a single metric result inside :class:`TurnMetricsEntry`."""

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool
    cost: float
    input_tokens: int
    output_tokens: int


class TurnMetricsEntry(TypedDict):
    """Shape of one turn's report-ready metrics data."""

    trace_id: str
    session_id: str
    scenario_id: str
    turn_index: int
    total_turns: int
    input: str
    output: str
    routed_to: str
    metrics: list[TurnMetricResult]
