"""The document the interview builds.

A tree plus two reference lists:

    epics → behaviours → criteria     what should be true
    personas, tasks                   how we'll check it

`ProductProfile` is a pure artefact. It carries no step, no history and no session id, so it
can be hand-written in a fixture, rendered, compiled or diffed without an interview ever
having happened. Where the interview got to is `SessionState.step`, deliberately elsewhere.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from metis.wizard.domain.types import InteractionType

UNIVERSAL_EPIC_ID = "EP-UNI"


class EpicScope(StrEnum):
    PRODUCT = "product"  # discovered from the interview
    UNIVERSAL = "universal"  # arrives from the metric library, read-only


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
    summary: str  # what it does, for whom
    users: str  # prose — feeds persona proposal
    architecture: str = ""  # prose — the machinery: tools, delegation, memory, recovery


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


class Epic(BaseModel):
    id: str
    name: str
    scope: EpicScope = EpicScope.PRODUCT
    behaviours: list[Behaviour] = Field(default_factory=list)

    @property
    def is_universal(self) -> bool:
        return self.scope is EpicScope.UNIVERSAL


class Persona(Authored):
    id: str  # stable key, visible label, and what compiled tasks reference
    description: str


class Task(Authored):
    id: str
    description: str  # the situation
    behaviour_refs: list[str] = Field(default_factory=list)  # M:N — several per task
    persona_refs: list[str] = Field(default_factory=list)
    fixtures: list[str] = Field(
        default_factory=list
    )  # filenames only — no upload in MVP
    num_trials: int = 3  # one run of a non-deterministic agent says very little


class ProductProfile(BaseModel):
    """The whole document. Includes the universal epic in `epics`, not as a second list.

    Keeping universals in `epics` means every renderer, review.md and the compiler walk one
    list instead of special-casing a second, and `Behaviour` needs no scope of its own — it
    is derivable from the parent epic.
    """

    product: Product
    epics: list[Epic] = Field(default_factory=list)  # includes EP-UNI
    personas: list[Persona] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)

    # ── walking the tree ───────────────────────────────────────────────────

    def behaviours(self) -> list[Behaviour]:
        """Every behaviour, universal ones included, in document order."""
        return [b for epic in self.epics for b in epic.behaviours]

    def ticked(self) -> list[Behaviour]:
        """Product behaviours the user chose to measure.

        Universal behaviours are excluded: they are always on, ride along on every task, and
        are never the user's decision — so they are not what "ticked" means anywhere else.
        """
        return [
            b
            for epic in self.epics
            if not epic.is_universal
            for b in epic.behaviours
            if b.priority
        ]

    def universal_epic(self) -> Epic | None:
        return next((e for e in self.epics if e.is_universal), None)

    def universal_behaviours(self) -> list[Behaviour]:
        epic = self.universal_epic()
        return list(epic.behaviours) if epic else []

    def behaviour(self, behaviour_id: str) -> Behaviour | None:
        return next((b for b in self.behaviours() if b.id == behaviour_id), None)

    def epic(self, epic_id: str) -> Epic | None:
        """One epic by id — symmetric with `behaviour`, `persona` and `task`."""
        return next((e for e in self.epics if e.id == epic_id), None)

    def epic_of(self, behaviour_id: str) -> Epic | None:
        """Which epic owns a behaviour — how scope is derived without a field for it."""
        return next(
            (e for e in self.epics if any(b.id == behaviour_id for b in e.behaviours)),
            None,
        )

    def persona(self, persona_id: str) -> Persona | None:
        return next((p for p in self.personas if p.id == persona_id), None)

    def task(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def tasks_covering(self, behaviour_id: str) -> list[Task]:
        return [t for t in self.tasks if behaviour_id in t.behaviour_refs]

    def uncovered(self) -> list[Behaviour]:
        """Ticked behaviours no task exercises — the blocking gate at the tasks step."""
        return [b for b in self.ticked() if not self.tasks_covering(b.id)]

    def session_count(self) -> int:
        """Sessions the engine will run: Σ over tasks of (personas × trials).

        Mirrors the harness expansion exactly, so the footer the user reads during the
        interview and the number of runs they actually pay for cannot disagree.
        """
        return sum(len(t.persona_refs) * t.num_trials for t in self.tasks)

    # ── persistence ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> ProductProfile:
        return cls.model_validate_json(Path(path).read_text())

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.model_dump(mode="json"), indent=2) + "\n")
