"""Pydantic models for simulation types.

Covers simulation inputs and runner action and observation types.
Trial records live in ``metis.core.trials``. The specification schema is
published by metis-core. See ``packages/core/schemas/README.md``.
"""

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from metis.core import Artifact
from metis.core.experiment import Task
from metis.core.specification import Specification as CoreSpecification
from metis.core.trials import GraderRef


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
# UI State (captured from the target)
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
    """Complete UI state captured after a target response."""

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
    """What the target returned after a turn (transport-agnostic).

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


class TrialMeta(BaseModel):
    """Metadata about the current trial state."""

    turn_number: int
    elapsed_seconds: int


class UserAgentInput(BaseModel):
    """Input to :pymeth:`UserAgent.generate_response`."""

    observation: Observation = Field(default_factory=Observation)
    trial_meta: TrialMeta | None = None


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


class Persona(BaseModel, extra="ignore"):
    id: str
    description: str


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


class Scenario(BaseModel):
    task_id: str = ""
    id: str
    description: str
    num_trials: int = 1
    fixtures: list[str] = Field(default_factory=list)
    persona_refs: list[str] = Field(min_length=1)
    grader_refs: list[GraderRef] = Field(default_factory=list)
    max_turns: int = 20
    timeout_minutes: int = 15
    response_wait_ms: int = 300000
    max_trial_retries: int | None = None

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


class Specification(CoreSpecification):
    """A complete Specification validated for engine execution."""

    @model_validator(mode="before")
    @classmethod
    def _require_header(cls, data: Any) -> Any:
        # drafts take defaults for these keys; a file the engine runs must state them.
        if isinstance(data, dict) and not {"profile", "experiment"} & data.keys():
            missing = [
                key
                for key in ("schema_version", "id", "runner_factory_ref")
                if key not in data
            ]
            if missing:
                raise ValueError(
                    f"The specification needs these keys: {', '.join(missing)}."
                )
        return data

    @model_validator(mode="after")
    def _check_execution(self) -> Self:
        errors = self.execution_errors()
        if errors:
            raise ValueError(" ".join(errors))
        from .runner_resolver import resolve_runner_factory

        try:
            resolve_runner_factory(self.runner_factory_ref)
        except (ImportError, TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self

    def resolved_tasks(self) -> list[Scenario]:
        return [self.resolve_task(task) for task in self.tasks]

    def resolve_task(self, task: Task) -> Scenario:
        scenario = self.scenario(task.scenario_ref)
        assert scenario is not None
        refs = []
        for behaviour_id in task.behaviour_refs:
            behaviour = self.behaviour(behaviour_id)
            assert behaviour is not None
            for criterion in behaviour.criteria:
                assert criterion.grader_fqn
                refs.append(
                    GraderRef(
                        criterion_id=criterion.id,
                        fqn=criterion.grader_fqn,
                        args=criterion.grader_args,
                    )
                )
        return Scenario(
            id=scenario.id,
            task_id=task.id,
            description=scenario.description,
            persona_refs=[task.persona_ref],
            num_trials=task.num_trials,
            max_turns=task.max_turns,
            timeout_minutes=task.timeout_minutes,
            response_wait_ms=task.response_wait_ms,
            max_trial_retries=task.max_run_retries,
            fixtures=task.fixtures,
            grader_refs=refs,
        )

    @classmethod
    def load_file(cls, path: Path) -> Self:
        import yaml

        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
