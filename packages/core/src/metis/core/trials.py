"""record.json: what one trial of ``metis engine simulate`` recorded.

Each trial writes one ``TrialRecord`` to ``outputs/trials/<trial>/record.json``: the trial's
config, how it ended, the artifacts the target produced, the Langfuse session holding the
conversation, and the retry history. ``metis engine evaluate`` and ``--resume`` read it back,
and so does ``metis insights report``.

The models live in metis-core because the engine writes them and the report reads them, and
``metis-insights`` may depend only on ``metis-core``. ``GraderRef`` is here because
``TrialConfig.grader_refs`` holds it; the engine's ``Scenario`` reuses it. TrialRecord is
code-produced, like ``EvaluationResults``, so it has no published JSON Schema file. Its version
constant is ``_TRIAL_RECORD_VERSION``.
"""

import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema as cs

from metis.core.artifacts import Artifact
from metis.core.profile import CriterionText

_TRIAL_RECORD_VERSION = 1


class GraderRef(BaseModel):
    """A grader reference from specification.yaml.

    Accepts either:
      - a plain string: "metis.library.graders.demo.DemoTraceBudgetGrader"
      - a single-key mapping: {"metis.library.graders.demo.DemoTraceBudgetGrader": {"max_traces": 8}}
    """

    criterion_id: str = ""
    fqn: str = Field(
        description=(
            "Fully-qualified import path of the grader class to run — a"
            " metis.library.grader.Grader subclass, e.g."
            " 'metis.library.graders.demo.DemoTraceBudgetGrader'. Resolved at"
            " runtime via importlib."
        )
    )
    args: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "The grader's arguments, validated against its args_model before"
            " the run (unknown keys are rejected). Empty when the grader's"
            " defaults suffice."
        ),
    )
    description: CriterionText | None = Field(
        default=None,
        description=(
            "The criterion description. A grader that takes its instructions"
            " from the criterion receives it as grader_args.criterion."
        ),
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: cs.CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        return {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                {
                    "type": "object",
                    "properties": {
                        "fqn": {"type": "string"},
                        "args": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["fqn"],
                },
            ],
            "description": (
                "A grader reference. Accepts a plain FQN string,"
                " a single-key mapping {FQN: {args}}, or"
                " {fqn: str, args: dict}."
            ),
        }

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, data: object) -> object:
        if isinstance(data, str):
            return {"fqn": data, "args": {}}
        if isinstance(data, dict):
            # Legacy / session-record internal format: {class: FQN, args: {...}}
            if "class" in data:
                return {"fqn": data["class"], "args": data.get("args") or {}}
            # New format: single-key mapping {FQN: args_dict}
            items = list(data.items())
            if len(items) == 1:
                fqn, args = items[0]
                return {"fqn": fqn, "args": args or {}}
        return data


class TrialConfig(BaseModel, extra="ignore"):
    """Environment spec for a simulation run — defines which persona/scenario pair to run and the resource limits (turn cap, timeout) that bound execution."""

    task_id: str = ""
    trial_index: int = 1
    persona: str
    scenario: str
    grader_refs: list[GraderRef] = Field(default_factory=list)
    max_turns: int = 20
    timeout_minutes: int = 15
    response_wait_ms: int = 300000
    fixtures: list[str] = Field(default_factory=list)


class TrialOutcome(BaseModel, extra="ignore"):
    stop_reason: str
    total_turns: int
    duration_seconds: float
    failure_source: str | None = None
    """Which party caused a failed trial, such as ``"target"``, ``"user_agent"`` or
    ``"evaluation_runner"``. ``None`` when the trial succeeded or no cause is known."""
    failure_message: str | None = None
    """The latest problem behind ``failure_source``, as one line for the report. ``None``
    whenever ``failure_source`` is."""


class TrialFailure(BaseModel, extra="ignore"):
    attempt_number: int
    failure_type: str
    submission_phase: Literal["pre", "post", "unknown"] = "unknown"
    turn_reached: int
    error_message: str
    duration_ms: int


class TrialRecord(BaseModel, extra="ignore"):
    """A complete simulation run record loaded from a JSON result file."""

    schema_version: Literal[1] = _TRIAL_RECORD_VERSION
    config: TrialConfig
    outcome: TrialOutcome
    artifacts: list[Artifact] = []
    target_session_id: str | None = None
    # attempt_number is telemetry: which attempt produced this record.
    # max_allowed_attempts is configuration: 1 + the run's retry budget.
    # A record with attempt_number=1 and max_allowed_attempts=3 succeeded on
    # the first try under a budget of three — it did not take three attempts.
    # prior_failures holds one TrialFailure per attempt that failed. It is not
    # strictly "prior": on a record whose retry budget ran out, the failure of
    # this record's own attempt is appended before the record is stamped, so the
    # last entry can describe attempt_number itself. Never compute attempts-made
    # as 1 + len(prior_failures).
    attempt_number: int = 1
    max_allowed_attempts: int = 1
    prior_failures: list[TrialFailure] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _check_version(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        v = data.get("schema_version")
        if v is not None and v != _TRIAL_RECORD_VERSION:
            raise ValueError(
                f"Unsupported schema_version {v!r} (expected {_TRIAL_RECORD_VERSION}). "
                f"This record was produced by a different version of metis-engine."
            )
        return data

    @classmethod
    def load_file(cls, path: Path) -> Self:
        with open(path, encoding="utf-8") as fh:
            return cls.model_validate(json.load(fh))
