"""Report-ready data types.

The evaluation pipeline produces structured results (TurnResult, SessionResult)
that hold deepeval test case objects — rich but not JSON-serializable. These
TypedDicts are the serializable projection used by the reporting layer:

  TurnResult  ──► TurnReport   (one per trace/turn)
  SessionResult ──► SessionReport (one per session)

The conversion happens in generator._convert_turn_results and
generator._convert_session_results. Downstream, these dicts are:
  • aggregated for pass/fail/skip counts (_aggregation.py)
  • rendered into HTML tables and trace detail views (_html_sections.py)
  • serialized directly to the JSON report file (generator.py)
"""

from __future__ import annotations

from typing_extensions import TypedDict


class SessionMetricResult(TypedDict):
    """Shape of a single metric result inside :class:`SessionReport`."""

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool


class SessionReport(TypedDict):
    """Report-ready projection of a SessionResult.

    Only carries the fields consumed by aggregation and JSON output.
    Session-level conversation content (turns, tool calls) is not included —
    it's available in the source SessionResult.conversational_test_case if needed.
    """

    session_id: str
    metrics: list[SessionMetricResult]


class TurnMetricResult(TypedDict, total=False):
    """Shape of a single metric result inside :class:`TurnReport`."""

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool
    cost: float
    input_tokens: int
    output_tokens: int


class TurnReport(TypedDict):
    """Report-ready projection of a TurnResult.

    Every field is consumed by the HTML renderer (trace details, task sections,
    failure extraction) — none are pass-through-only.
    """

    trace_id: str
    session_id: str
    scenario_id: str
    turn_index: int
    total_turns: int
    input: str
    output: str
    routed_to: str
    metrics: list[TurnMetricResult]


class PersonaContext(TypedDict, total=False):
    """Per-persona outcome data attached to a task context."""

    id: str
    description: str
    stop_reason: str
    total_turns: int
    duration_seconds: float


class TaskContext(TypedDict, total=False):
    """Contextual metadata for a scenario/task in the report."""

    description: str
    persona_id: str
    persona_description: str
    fixtures: list[str]
    stop_reason: str
    total_turns: int
    duration_seconds: float
    personas: list[PersonaContext]
