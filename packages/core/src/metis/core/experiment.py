"""Experiment plan: Personas, Scenarios, Tasks, and execution settings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer

from metis.core.profile import NamedNode


class Persona(NamedNode[str]):
    """A user type whose id can differ from its display name."""

    metadata: dict[str, str] = Field(default_factory=dict)


class Scenario(NamedNode[str], extra="forbid"):
    """The situation in which Tasks evaluate the target."""

    metadata: dict[str, str] = Field(default_factory=dict)


class Task(BaseModel, extra="forbid"):
    """One test case. Identity survives edits to its references and inputs."""

    id: str
    scenario_ref: str
    persona_ref: str
    fixtures: list[str] = Field(default_factory=list)
    num_trials: int = Field(default=3, strict=True)
    behaviour_refs: list[str] = Field(default_factory=list)
    max_turns: int = Field(default=20, gt=0, strict=True)
    timeout_minutes: int = Field(default=15, gt=0, strict=True)
    response_wait_ms: int = Field(default=300000, gt=0, strict=True)
    max_run_retries: int | None = Field(default=None, ge=0, strict=True)


class ExperimentDefaults(BaseModel, extra="forbid"):
    """Experiment-wide defaults that individual criteria can override."""

    judge_model: str | None = Field(default=None, min_length=1)
    """The judge model for every model-based grader whose criterion does not set
    ``grader_args.model``. When unset, the engine falls back to ``JUDGE_MODEL`` and then to its
    package default."""


class Experiment(BaseModel):
    """The Test Cases and settings used to execute an evaluation."""

    id: str = ""
    runner_factory_ref: str = (
        "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
    )
    defaults: ExperimentDefaults = Field(default_factory=ExperimentDefaults)
    personas: list[Persona] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    fixture_content_descriptions: dict[str, str] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _omit_empty_defaults(self, handler: SerializerFunctionWrapHandler) -> Any:
        """Leave ``defaults`` out until one is set, so existing specs serialise unchanged."""
        data = handler(self)
        if isinstance(data, dict) and not self.defaults.model_dump(exclude_none=True):
            data.pop("defaults", None)
        return data

    def persona(self, persona_id: str) -> Persona | None:
        return next((p for p in self.personas if p.id == persona_id), None)

    def scenario(self, scenario_id: str) -> Scenario | None:
        return next((s for s in self.scenarios if s.id == scenario_id), None)

    def task(self, task_id: str) -> Task | None:
        return next((task for task in self.tasks if task.id == task_id), None)

    def trial_count(self) -> int:
        return sum(task.num_trials for task in self.tasks)
