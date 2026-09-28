"""Pydantic models for simulation types.

Covers both inputs (personas, experiments) and outputs (run records).
These are the source of truth for the JSON Schemas in schemas/. After any
change here, run `make generate-schema` and commit the updated schema files.
"""

import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema as cs

from metis.core import Artifact

_EXPERIMENT_VERSION = 2
_RUN_RECORD_VERSION = 2


# ---------------------------------------------------------------------------
# User Agent Output — self-describing action union
#
# Each action carries a ``slot_id`` naming the :class:`ActionSlot` the persona
# chose from the previous turn's ``Observation.available_actions``. The link is
# a runtime contract, not a schema constraint: the persona is an LLM and may
# emit an id that was never offered, so a runner re-validates on dispatch and
# skips a stray form/button action. What an id denotes is runner-defined (a
# form-field id, a DOM selector, …).
#
# Uploads are the exception: a runner routes on ``filename`` (the fixture),
# never ``slot_id``. Whether an upload's ``slot_id`` corresponds to a real slot
# is therefore runner-dependent — the Orca-API runner offers a ``file_upload``
# slot per fixture (so ``slot_id`` == ``filename`` == the slot id there), while
# the Playwright runner offers no upload slots at all (its ``available_actions``
# are DOM form elements only), so an upload's ``slot_id`` matches nothing on
# offer. Treat ``slot_id`` as advisory for uploads.
# ---------------------------------------------------------------------------


class UploadFileAction(BaseModel, extra="forbid"):
    """Attach a fixture file to this turn."""

    type: Literal["upload_file"] = "upload_file"
    slot_id: str = Field(
        description=(
            "Id of the file_upload ActionSlot chosen. Advisory: runners attach"
            " by `filename`, and not every runner offers upload slots."
        )
    )
    filename: str = Field(description="Name of the scenario fixture to attach.")


class ButtonClickAction(BaseModel, extra="forbid"):
    """Activate a button-like offered slot (no payload)."""

    type: Literal["button_click"] = "button_click"
    slot_id: str = Field(
        description="Id of the ActionSlot to activate, from available_actions."
    )


class FormFillAction(BaseModel, extra="forbid"):
    """Answer an offered form field with a typed value."""

    type: Literal["form_fill"] = "form_fill"
    slot_id: str = Field(
        description=(
            "Id of the form-field ActionSlot to answer, from available_actions."
        )
    )
    value: str | list[str] | int | float = Field(
        description="The typed answer for the field."
    )


#: The self-describing action union the persona emits. A plain ``anyOf`` union
#: (each variant carries a ``type`` literal) — NOT a Pydantic discriminated
#: union: ``Field(discriminator=...)`` emits ``oneOf`` + ``discriminator``,
#: which is outside OpenAI's strict structured-output subset. Runners dispatch
#: in Python via ``match`` / ``isinstance``.
ChosenAction = UploadFileAction | ButtonClickAction | FormFillAction


# ---------------------------------------------------------------------------
# Transport-Agnostic Action Protocol
# ---------------------------------------------------------------------------


class ActionSlot(BaseModel):
    """A single action the runner can execute, discovered per-turn."""

    id: str
    kind: str
    label: str
    options: list[str] | None = None
    required: bool | None = None


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
    actions: list[ChosenAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# UI State (captured from the target system)
# ---------------------------------------------------------------------------


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


class ActionResult(BaseModel):
    """The runner's first-hand verdict on one action it was handed.

    One row per action the runner received, in the order received, with
    ``action_index`` equal to the row's own position (invariant I1). The
    verdict is about *delivery*, not about whether the target liked what was
    delivered: a file that uploaded cleanly and was then refused by a
    guardrail is ``succeeded=True`` plus a note in
    :attr:`Observation.response_notices`.
    """

    action_index: int
    succeeded: bool
    detail: str = ""
    retryable: bool | None = None
    withheld: bool = False

    @model_validator(mode="after")
    def _failure_needs_detail(self) -> Self:
        if not self.succeeded and not self.detail.strip():
            raise ValueError(
                "an ActionResult with succeeded=False MUST carry a non-empty `detail`"
            )
        return self

    @model_validator(mode="after")
    def _retryable_only_on_failure(self) -> Self:
        if self.succeeded and self.retryable is not None:
            raise ValueError(
                "`retryable` describes a delivery failure; it MUST be None when"
                " succeeded is True"
            )
        return self


class Observation(BaseModel):
    """What the target system returned after a turn (transport-agnostic).

    Each field has exactly one owner, and the owner is what the field
    describes — see ``docs/runner-contract.md``. ``action_results`` belongs to
    the persona's actions, ``text`` and ``artifacts`` to the target,
    ``response_notices`` to the turn as a whole, ``available_actions`` to
    what the target is offering next, and ``delivered`` to whether this turn
    was actually submitted to the target and accepted by it, as opposed to
    being declined or rejected — a post-condition on the outcome, not a
    claim about how many transport operations the runner used to reach it
    (I5).
    """

    text: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)
    response_notices: list[str] = Field(default_factory=list)
    action_results: list[ActionResult] = Field(default_factory=list)
    available_actions: list[ActionSlot] | None = None
    status_labels: list[str] = Field(default_factory=list)
    discarded_message: str | None = None
    delivered: bool = True


# ---------------------------------------------------------------------------
# User Agent Input
# ---------------------------------------------------------------------------


class RunMeta(BaseModel):
    """Metadata about the current run state."""

    turn_number: int
    elapsed_seconds: int


class UserAgentInput(BaseModel):
    """Input to :pymeth:`UserAgent.generate_response`."""

    observation: Observation = Field(default_factory=Observation)
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

    fqn: str = Field(
        description=(
            "Fully-qualified import path of the metric class to run — a"
            " MetisTurnMetric or MetisSessionMetric subclass, e.g."
            " 'metis.library.metrics.RoutingAccuracyMetric'. Resolved at"
            " runtime via importlib."
        )
    )
    args: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Keyword arguments for the metric's constructor (invoked as"
            " cls(**args)), mapping each parameter name to its value. Empty"
            " when the metric takes no configuration."
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
    max_turns: int = 20
    timeout_minutes: int = 15
    response_wait_ms: int = 300000
    max_run_retries: int | None = None

    @model_validator(mode="after")
    def _check_unique_fixtures(self) -> Self:
        seen: set[str] = set()
        dupes: list[str] = []
        for name in self.fixtures:
            if name in seen:
                dupes.append(name)
            seen.add(name)
        if dupes:
            raise ValueError(
                f"Scenario '{self.id}' lists duplicate fixture(s): "
                f"{sorted(set(dupes))}. Each fixture name must appear at most once."
            )
        return self

    @model_validator(mode="after")
    def _check_unique_persona_refs(self) -> Self:
        seen: set[str] = set()
        dupes: list[str] = []
        for ref in self.persona_refs:
            if ref in seen:
                dupes.append(ref)
            seen.add(ref)
        if dupes:
            raise ValueError(
                f"Scenario '{self.id}' lists duplicate persona_ref(s): "
                f"{sorted(set(dupes))}. Each persona_ref must appear at most once."
            )
        return self


class Experiment(BaseModel):
    schema_version: Literal[
        2
    ]  # required — no default; see schemas/README.md for bump rules
    id: str
    description: str
    runner_factory_ref: str = Field(
        min_length=1,
        description="FQN of a RunnerFactory class (e.g. metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory)",
    )
    personas: list[Persona] = Field(min_length=1)
    scenarios: list[Scenario] = Field(min_length=1)
    fixture_content_descriptions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional map of fixture filename → Artifact.content_description."
            " Fixtures not listed here are auto-summarized at run start."
        ),
    )

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
                "Update your experiment.yaml to the current schema version."
            )
        return data

    @model_validator(mode="after")
    def _check_persona_refs(self) -> Self:
        defined = {p.id for p in self.personas}
        for scenario in self.scenarios:
            missing = [ref for ref in scenario.persona_refs if ref not in defined]
            if missing:
                raise ValueError(
                    f"Scenario '{scenario.id}' references undefined persona(s): {missing}"
                )
        return self

    @model_validator(mode="after")
    def _validate_runner_factory_ref(self) -> Self:
        from .runner_resolver import resolve_runner_factory

        try:
            resolve_runner_factory(self.runner_factory_ref)
        except (ImportError, TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self

    @classmethod
    def load_file(cls, path: Path) -> Self:
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
    fixtures: list[str] = Field(default_factory=list)


class RunOutcome(BaseModel, extra="ignore"):
    stop_reason: str
    total_turns: int
    duration_seconds: float


class ActionRetry(BaseModel, extra="ignore"):
    action: str
    attempt: int
    strategy_used: str
    error: str
    duration_ms: int


class TurnDiagnostics(BaseModel, extra="ignore"):
    retry_count: int = 0
    failure_type: str | None = None
    submission_phase: Literal["pre", "post", "n/a"] = "n/a"
    action_retries: list[ActionRetry] = Field(default_factory=list)
    duration_ms: int = 0
    discarded_message: str | None = None


class RunFailure(BaseModel, extra="ignore"):
    attempt_number: int
    failure_type: str
    submission_phase: Literal["pre", "post", "unknown"] = "unknown"
    turn_reached: int
    error_message: str
    duration_ms: int


class ConversationTurn(BaseModel, extra="ignore"):
    turn_number: int
    user_message: str
    target_response: dict[str, Any] = {}
    duration_ms: int = 0
    timestamp: str = ""
    user_ui_actions: list[dict[str, Any]] = []
    diagnostics: TurnDiagnostics | None = None


class RunRecord(BaseModel, extra="ignore"):
    """A complete simulation run record loaded from a JSON result file."""

    schema_version: Literal[2] = _RUN_RECORD_VERSION
    config: RunConfig
    outcome: RunOutcome
    conversation: list[ConversationTurn] = []
    artifacts: list[Artifact] = []
    target_session_id: str | None = None
    # attempt_number is telemetry: which attempt produced this record.
    # max_allowed_attempts is configuration: 1 + the run's retry budget.
    # A record with attempt_number=1 and max_allowed_attempts=3 succeeded on
    # the first try under a budget of three — it did not take three attempts.
    # prior_failures holds one RunFailure per attempt that failed. It is not
    # strictly "prior": on a record whose retry budget ran out, the failure of
    # this record's own attempt is appended before the record is stamped, so the
    # last entry can describe attempt_number itself. Never compute attempts-made
    # as 1 + len(prior_failures).
    attempt_number: int = 1
    max_allowed_attempts: int = 1
    prior_failures: list[RunFailure] = Field(default_factory=list)

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
    def load_file(cls, path: Path) -> Self:
        with open(path) as fh:
            return cls.model_validate(json.load(fh))
