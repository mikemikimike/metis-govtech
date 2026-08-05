"""Pydantic models for simulation types.

Covers both inputs (personas, experiments) and outputs (run records).
These are the source of truth for the JSON Schemas in schemas/. After any
change here, run `make generate-schema` and commit the updated schema files.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema as cs

_EXPERIMENT_VERSION = 1
_RUN_RECORD_VERSION = 1


# ---------------------------------------------------------------------------
# User Agent Output
# ---------------------------------------------------------------------------


class FileUploadAction(BaseModel):
    """Upload a fixture file."""

    type: Literal["file_upload"] = "file_upload"
    file: str


class ButtonClickAction(BaseModel):
    """Click a button by selector."""

    type: Literal["button_click"] = "button_click"
    selector: str


class FormFillAction(BaseModel):
    """Fill a form element by selector."""

    type: Literal["form_fill"] = "form_fill"
    selector: str
    value: str


UIAction = FileUploadAction | ButtonClickAction | FormFillAction


class UserAgentOutput(BaseModel):
    """Output of a single user-agent turn (opening or follow-up)."""

    reasoning: str = Field(
        default="",
        description=(
            "Internal thought process: why this decision/message was"
            " chosen given the persona, task progress, and target"
            " response."
        ),
    )
    message: str
    decision: Literal["continue", "goal_achieved", "giving_up"] = "continue"
    ui_actions: list[UIAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# UI State (captured from the target system)
# ---------------------------------------------------------------------------


class Artifact(BaseModel):
    """A downloadable item detected in the UI."""

    name: str
    type: Literal["download", "preview", "chart"]
    url: str | None = None


class FormElement(BaseModel):
    """A form element extracted from the page."""

    type: Literal["input", "select", "radio", "checkbox", "button", "textarea"]
    label: str
    selector: str
    value: str | None = None
    options: list[str] | None = None
    checked: bool | None = None
    placeholder: str | None = None


class UIState(BaseModel):
    """Complete UI state captured after a target system response."""

    text: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)
    target_status_labels: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    interactive_elements: list[str] = Field(default_factory=list)
    form_elements: list[FormElement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# User Agent Input
# ---------------------------------------------------------------------------


class RunMeta(BaseModel):
    """Metadata about the current run state."""

    turn_number: int
    elapsed_seconds: int


class UserAgentInput(BaseModel):
    """Input to :pymeth:`UserAgent.generate_response`."""

    ui_state: UIState = Field(default_factory=UIState)
    run_meta: RunMeta | None = None


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


class Persona(BaseModel, extra="ignore"):
    id: str
    description: str


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


class MetricRef(BaseModel):
    """A metric reference from experiment.yaml.

    Accepts either:
      - a plain string: "metis.library.metrics.RoutingAccuracyMetric"
      - a single-key mapping: {"metis.library.metrics.TurnBudgetMetric": {"max_turns": 8}}
    """

    fqn: str
    args: dict = Field(default_factory=dict)

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
                "A metric reference. Accepts a plain FQN string,"
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


class Scenario(BaseModel):
    id: str
    description: str
    num_trials: int = 1
    fixtures: list[str] = Field(default_factory=list)
    persona_refs: list[str] = Field(min_length=1)
    metric_refs: list[MetricRef] = Field(default_factory=list)
    response_wait_ms: int = 300000


class Experiment(BaseModel):
    schema_version: Literal[
        1
    ]  # required — no default; see schemas/README.md for bump rules
    id: str
    description: str
    personas: list[Persona] = Field(min_length=1)
    scenarios: list[Scenario] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _check_version(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        v = data.get("schema_version")
        if v is None:
            raise ValueError(
                "Missing required field 'schema_version'. "
                f"Add 'schema_version: {_EXPERIMENT_VERSION}' to your experiment.yaml."
            )
        if v != _EXPERIMENT_VERSION:
            raise ValueError(
                f"Unsupported schema_version {v!r} (expected {_EXPERIMENT_VERSION}). "
                "Update your experiment.yaml or migrate to the current schema version."
            )
        return data

    @model_validator(mode="after")
    def _check_persona_refs(self) -> "Experiment":
        defined = {p.id for p in self.personas}
        for scenario in self.scenarios:
            missing = [ref for ref in scenario.persona_refs if ref not in defined]
            if missing:
                raise ValueError(
                    f"Scenario '{scenario.id}' references undefined persona(s): {missing}"
                )
        return self

    @classmethod
    def load_file(cls, path: Path) -> "Experiment":
        import yaml

        return cls.model_validate(yaml.safe_load(path.read_text()))


# ---------------------------------------------------------------------------
# Run Record (simulation output)
# ---------------------------------------------------------------------------


class RunConfig(BaseModel, extra="ignore"):
    """Environment spec for a simulation run — defines which persona/scenario pair to run and the resource limits (turn cap, timeout) that bound execution."""

    persona: str
    scenario: str
    metric_refs: list[MetricRef] = Field(default_factory=list)
    max_turns: int = 20
    timeout_minutes: int = 15
    response_wait_ms: int = 300000


class RunOutcome(BaseModel, extra="ignore"):
    stop_reason: str
    total_turns: int
    duration_seconds: float


class CollectedArtifact(BaseModel, extra="ignore"):
    filename: str
    collected_at_turn: int
    path: str = ""


class ConversationTurn(BaseModel, extra="ignore"):
    turn_number: int
    user_message: str
    target_response: dict
    duration_ms: int
    timestamp: str
    user_ui_actions: list[dict] = []


class RunRecord(BaseModel, extra="ignore"):
    """A complete simulation run record loaded from a JSON result file."""

    schema_version: Literal[1] = _RUN_RECORD_VERSION
    config: RunConfig
    outcome: RunOutcome
    conversation: list[ConversationTurn] = []
    artifacts_collected: list[CollectedArtifact] = []
    target_session_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _check_version(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        v = data.get("schema_version")
        if v is not None and v != _RUN_RECORD_VERSION:
            raise ValueError(
                f"Unsupported schema_version {v!r} (expected {_RUN_RECORD_VERSION}). "
                f"This record was produced by a different version of metis-engine."
            )
        return data

    @classmethod
    def load_file(cls, path: Path) -> "RunRecord":
        with open(path) as fh:
            return cls.model_validate(json.load(fh))
