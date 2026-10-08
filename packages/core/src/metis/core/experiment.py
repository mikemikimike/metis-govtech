"""Experiment plan: Personas, Scenarios, Tasks, and execution settings."""

from __future__ import annotations

from pydantic import BaseModel, Field

from metis.core.profile import NamedNode


class Persona(NamedNode[str]):
    """A user type whose id can differ from its display name."""


class Scenario(NamedNode[str], extra="forbid"):
    """The situation in which Tasks evaluate the product."""


class Task(BaseModel, extra="forbid"):
    """One test case. Identity survives edits to its references and inputs."""

    id: str
    scenario_ref: str
    persona_ref: str
    fixtures: list[str] = Field(default_factory=list)
    num_trials: int = Field(default=3, strict=True)
    criterion_refs: list[str] = Field(default_factory=list)


class Experiment(BaseModel):
    """The Test Cases and settings used to execute an evaluation."""

    id: str = ""
    runner_factory_ref: str = (
        "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
    )
    personas: list[Persona] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    fixture_content_descriptions: dict[str, str] = Field(default_factory=dict)

    def persona(self, persona_id: str) -> Persona | None:
        return next((p for p in self.personas if p.id == persona_id), None)

    def scenario(self, scenario_id: str) -> Scenario | None:
        return next((s for s in self.scenarios if s.id == scenario_id), None)

    def task(self, task_id: str) -> Task | None:
        return next((task for task in self.tasks if task.id == task_id), None)

    def trial_count(self) -> int:
        return sum(task.num_trials for task in self.tasks)
