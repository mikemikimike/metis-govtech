"""results.json: every grader record from one evaluation of an experiment directory.

`metis engine evaluate` runs each criterion's grader once per session, applies the criterion's
threshold to every ``GraderResult`` the grader returned, and writes one ``GraderRecord`` per
grader per session. A record holds one ``RecordedResult`` per grading scope the grader chose: a
per-trace grader over a 10-trace session contributes 10 results, a session grader 1, so a
report should show each result count beside its rate.

The models live in metis-core because the engine writes them and the report reads them.
EvaluationResults is code-produced, like TrialRecord, so it has no published JSON Schema file.
Its version constant is ``_EVALUATION_RESULTS_VERSION``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from metis.core.grading import RecordedResult

if TYPE_CHECKING:
    from pathlib import Path

_EVALUATION_RESULTS_VERSION = 2


class GraderRecord(BaseModel):
    """One grader run on one session: the run facts plus every result it produced."""

    session_id: str
    scenario_id: str
    task_id: str
    trial_index: int
    criterion_id: str
    grader_fqn: str
    grader_args: dict[str, Any]
    """The validated args, defaults and resolved judge model included."""
    results: list[RecordedResult] = Field(min_length=1)


class EvaluationResults(BaseModel, extra="ignore"):
    """Every grader record from one evaluation of an experiment directory."""

    schema_version: Literal[2] = _EVALUATION_RESULTS_VERSION
    run_id: str
    records: list[GraderRecord] = Field(default_factory=list)
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
