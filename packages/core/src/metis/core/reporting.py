"""Evaluation results handed from metis-engine to metis-insights.

The evaluation pipeline produces structured results (TurnResult, SessionResult)
that hold deepeval test case objects — rich but not JSON-serializable. These
Pydantic models are their serializable projection:

  TurnResult    ──► TurnReport    (one per trace/turn)
  SessionResult ──► SessionReport (one per session)

`metis engine evaluate` performs that conversion, wraps the result in
EvaluationResults, and writes it to `<experiment>/reports/results.json`.
`metis insights report` reads the file back and builds the target evaluation
report from it. The models live in metis-core because it is the only package
both sides may import.

EvaluationResults is code-produced, like TrialRecord, so it has no published
JSON Schema file. Its version constant is `_EVALUATION_RESULTS_VERSION`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from pathlib import Path

_EVALUATION_RESULTS_VERSION = 2


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


class EvaluationResults(BaseModel, extra="ignore"):
    """Every grader result from one evaluation of an experiment directory."""

    schema_version: Literal[2] = _EVALUATION_RESULTS_VERSION
    run_id: str
    turn_results: list[TurnReport] = Field(default_factory=list)
    session_results: list[SessionReport] = Field(default_factory=list)
    routing: dict[str, Any] = Field(default_factory=dict)
    timings: dict[str, Any] = Field(default_factory=dict)
    latency_seconds: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _check_version(cls, data: object) -> object:
        """Reject only an explicit version we cannot read; a missing key takes the default."""
        if not isinstance(data, dict):
            return data
        v = data.get("schema_version")
        if v is not None and v != _EVALUATION_RESULTS_VERSION:
            raise ValueError(
                f"Unsupported schema_version {v!r} (expected {_EVALUATION_RESULTS_VERSION}). "
                "This results file was produced by a different version of metis-engine."
            )
        return data

    @classmethod
    def load_file(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        """Write the results as UTF-8 JSON, creating the parent directory."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")
