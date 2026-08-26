"""The document the interview builds.

A tree plus two reference lists:

    tasks → behaviours → criteria     what should be true
    personas, scenarios               how we'll check it

`ProductProfile` is a pure artefact. It carries no step, no history and no session id, so it
can be hand-written in a fixture, rendered, compiled or diffed without an interview ever
having happened. Where the interview got to is `SessionState.step`, deliberately elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from metis.wizard.domain.types import InteractionType


class Authored(BaseModel):
    """Anything whose text was written by the model or typed by the user.

    FORM means the user typed it and it is used as-is: the model never rewrites it, and the
    wizard asks before discarding it. Only CHAT and FORM ever appear here — a CHOICE applies
    a patch the model had already written, so it never produces prose of its own.
    """

    interaction_type: InteractionType = InteractionType.CHAT

    @property
    def is_user_typed(self) -> bool:
        """True when this text must survive a regeneration byte-identical."""
        return self.interaction_type is InteractionType.FORM


class Product(BaseModel):
    name: str
    users: str  # prose — who the product serves
    summary: str  # prose — the short description compiled into the experiment
    detail: str = ""  # prose — useful depth, including how the product works


class Criterion(Authored):
    id: str  # scoped to its behaviour — AC-1-1, AC-1-2
    given: str
    when: str
    then: str
    # resolved by the matcher, never by the model. `None` means matching has not run yet.
    metric_fqn: str | None = None
    metric_args: dict = Field(default_factory=dict)

    @property
    def text(self) -> str:
        """The three clauses as one string — what the matcher embeds."""
        return f"Given {self.given}, when {self.when}, then {self.then}."


class Behaviour(Authored):
    id: str
    statement: str
    # the user's tick, and the only real decision in the interview. The model never writes
    # it — the path is absent from StepPermissions entirely.
    priority: bool = False
    # criteria are kept when a behaviour is unticked — they go dormant rather than being
    # deleted, and the compiler filters on `priority` at the end. this is what lets the
    # tick stay live without needing any staleness tracking.
    criteria: list[Criterion] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    name: str
    behaviours: list[Behaviour] = Field(default_factory=list)


class Persona(Authored):
    id: str  # stable key, visible label, and what compiled scenarios reference
    description: str


class Scenario(Authored):
    id: str
    description: str  # the situation
    behaviour_refs: list[str] = Field(
        default_factory=list
    )  # M:N — several per scenario
    persona_refs: list[str] = Field(default_factory=list)
    fixtures: list[str] = Field(
        default_factory=list
    )  # filenames only; web fixture bytes live beside the session or in a request bundle
    num_trials: int = 3  # one run of a non-deterministic agent says very little


class ProductProfile(BaseModel):
    """The whole document. Every task in it was discovered from the interview."""

    product: Product
    tasks: list[Task] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)

    # ── walking the tree ───────────────────────────────────────────────────

    def behaviours(self) -> list[Behaviour]:
        """Every behaviour, in document order."""
        return [b for task in self.tasks for b in task.behaviours]

    def ticked(self) -> list[Behaviour]:
        """The behaviours the user chose to measure."""
        return [b for task in self.tasks for b in task.behaviours if b.priority]

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
        """Ticked behaviours no scenario exercises — the blocking gate at the scenarios step."""
        return [b for b in self.ticked() if not self.scenarios_covering(b.id)]

    def run_count(self) -> int:
        """Runs the engine will perform: Σ over scenarios of (personas × trials).

        Mirrors the harness expansion exactly, so the footer the user reads during the
        interview and the number of runs the engine performs cannot disagree.
        """
        return sum(len(s.persona_refs) * s.num_trials for s in self.scenarios)

    # ── persistence ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> ProductProfile:
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    def save(self, path: Path) -> None:
        Path(path).write_text(
            yaml.dump(
                self.model_dump(mode="json"),
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )
        )
