"""The document the interview builds.

A tree plus two reference lists:

    tasks → behaviours → criteria     what should be true
    personas, scenarios               how we'll check it

`ProductProfile` is a pure artefact. It carries no step, no history and no interview id, so it
can be hand-written in a fixture, rendered, compiled or diffed without an interview ever
having happened. The live pending request owns the current stage; otherwise, the application
derives the stage from Profile evidence and explicit confirmation values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generic, Literal, Self, TypeVar

import yaml
from pydantic import BaseModel, Field, model_validator

DescriptionT = TypeVar("DescriptionT")

# The profile.yaml schema version. Bump when a change makes an old profile fail to load; see
# packages/wizard/schemas/README.md for the rules.
_PROFILE_VERSION = 1


class ProfileNode(BaseModel, Generic[DescriptionT]):
    """A repeated profile entity with separate identity, label, and content."""

    id: str
    name: str
    description: DescriptionT


class Product(BaseModel):
    name: str
    users: str  # prose — who the product serves
    description: str  # prose — the short description compiled into the experiment
    detail: str = ""  # prose — useful depth, including how the product works


class CriterionDescription(BaseModel):
    given: str
    when: str
    then: str

    def __str__(self) -> str:
        """Return the clauses as the flat text used for metric matching."""
        return f"Given {self.given}, when {self.when}, then {self.then}."


class Criterion(ProfileNode[CriterionDescription]):
    # The id is scoped to its behaviour: AC-1-1, AC-1-2.
    # resolved by the matcher, never by the model. `None` means matching has not run yet.
    metric_fqn: str | None = None
    metric_args: dict[str, Any] = Field(default_factory=dict)


class Behaviour(ProfileNode[str]):
    # the user's tick, and the only real decision in the interview. The model never writes
    # it — the path is absent from StepPermissions entirely.
    measured: bool = False
    # criteria are kept when a behaviour is unticked — they go dormant rather than being
    # deleted, and the compiler filters on `measured` at the end. this is what lets the
    # tick stay live without needing any staleness tracking.
    criteria: list[Criterion] = Field(default_factory=list)


class Task(ProfileNode[str]):
    behaviours: list[Behaviour] = Field(default_factory=list)


class Persona(ProfileNode[str]):
    """A user type whose stable id can differ from its display name."""


class Scenario(ProfileNode[str]):
    behaviour_refs: list[str] = Field(
        default_factory=list
    )  # M:N — several per scenario
    persona_refs: list[str] = Field(default_factory=list)
    fixtures: list[str] = Field(
        default_factory=list
    )  # filenames only; web fixture bytes live beside the interview or in a specification request
    num_trials: int = 3  # one trial of a non-deterministic agent says very little


class ProductProfile(BaseModel):
    """The whole document. Every task in it was discovered from the interview."""

    # First field so it leads the serialized YAML, as experiment.yaml does. The profile is
    # machine-written and round-trips through this model, so the version is defaulted rather
    # than required: a profile without the key still loads and is stamped on the next save.
    schema_version: Literal[1] = _PROFILE_VERSION
    product: Product
    tasks: list[Task] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _check_version(cls, data: object) -> object:
        """Reject only an explicit version we cannot read; a missing key takes the default."""
        if not isinstance(data, dict):
            return data
        version = data.get("schema_version")
        if version is not None and version != _PROFILE_VERSION:
            raise ValueError(
                f"Unsupported schema_version {version!r} (expected {_PROFILE_VERSION}). "
                "This profile.yaml was written by a different version of metis-wizard."
            )
        return data

    # ── walking the tree ───────────────────────────────────────────────────

    def behaviours(self) -> list[Behaviour]:
        """Every behaviour, in document order."""
        return [b for task in self.tasks for b in task.behaviours]

    def measured_behaviours(self) -> list[Behaviour]:
        """The behaviours the user chose to measure."""
        return [b for task in self.tasks for b in task.behaviours if b.measured]

    def behaviour(self, behaviour_id: str) -> Behaviour | None:
        return next((b for b in self.behaviours() if b.id == behaviour_id), None)

    def task(self, task_id: str) -> Task | None:
        """One task by id — symmetric with `behaviour`, `persona` and `scenario`."""
        return next((t for t in self.tasks if t.id == task_id), None)

    def task_of(self, behaviour_id: str) -> Task | None:
        """Which task owns a behaviour — symmetric with `task` and `behaviour`."""
        return next(
            (t for t in self.tasks if any(b.id == behaviour_id for b in t.behaviours)),
            None,
        )

    def persona(self, persona_id: str) -> Persona | None:
        return next((p for p in self.personas if p.id == persona_id), None)

    def scenario(self, scenario_id: str) -> Scenario | None:
        return next((s for s in self.scenarios if s.id == scenario_id), None)

    def scenarios_covering(self, behaviour_id: str) -> list[Scenario]:
        return [s for s in self.scenarios if behaviour_id in s.behaviour_refs]

    def uncovered(self) -> list[Behaviour]:
        """Measured behaviours that no scenario exercises."""
        return [
            b for b in self.measured_behaviours() if not self.scenarios_covering(b.id)
        ]

    def trial_count(self) -> int:
        """Trials the engine will perform: Σ over scenarios of (personas × trials).

        Mirrors the harness expansion exactly, so the footer the user reads during the
        interview and the number of trials the engine performs cannot disagree.
        """
        return sum(len(s.persona_refs) * s.num_trials for s in self.scenarios)

    # ── persistence ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    def to_yaml(self) -> str:
        """Serialize the portable profile with the shared YAML format."""
        return yaml.dump(
            self.model_dump(mode="json"),
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_yaml())


def collect_profile_ids(profile: ProductProfile) -> set[str]:
    """Return every node and reference id present in a profile."""
    ids = {
        *(task.id for task in profile.tasks),
        *(behaviour.id for behaviour in profile.behaviours()),
        *(
            criterion.id
            for behaviour in profile.behaviours()
            for criterion in behaviour.criteria
        ),
        *(persona.id for persona in profile.personas),
        *(scenario.id for scenario in profile.scenarios),
        *(ref for scenario in profile.scenarios for ref in scenario.behaviour_refs),
        *(ref for scenario in profile.scenarios for ref in scenario.persona_refs),
    }
    return ids
