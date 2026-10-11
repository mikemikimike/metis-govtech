"""Report-ready data types.

The evaluation pipeline produces structured results (TurnResult, SessionResult)
that hold deepeval test case objects — rich but not JSON-serializable. These
Pydantic models are the serializable projection used by the reporting layer:

  TurnResult  ──► TurnReport   (one per trace/turn)
  SessionResult ──► SessionReport (one per session)

The conversion happens in generator._convert_turn_results and
generator._convert_session_results. Downstream, these models are:
  • aggregated for pass/fail/skip counts in the terminal summary (_aggregation.py)
  • joined onto the product specification to build the report (_report.py)
  • exported as part of the report JSON schema (schemas/report.schema.json)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionGraderResult(BaseModel):
    """Shape of a single grader result inside SessionReport."""

    criterion_id: str = ""
    grader_fqn: str = ""
    grader_args: dict[str, Any] = Field(default_factory=dict)
    task_id: str = ""
    trial_index: int = 1
    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool


class SessionReport(BaseModel):
    """Report-ready projection of a SessionResult."""

    session_id: str
    graders: list[SessionGraderResult]


class TurnGraderResult(BaseModel):
    """Shape of a single grader result inside TurnReport."""

    criterion_id: str = ""
    grader_fqn: str = ""
    grader_args: dict[str, Any] = Field(default_factory=dict)
    task_id: str = ""
    trial_index: int = 1
    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool
    cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class TurnReport(BaseModel):
    """Report-ready projection of a TurnResult."""

    trace_id: str
    session_id: str
    scenario_id: str
    turn_index: int
    total_turns: int
    input: str
    output: str
    routed_to: str
    graders: list[TurnGraderResult]
