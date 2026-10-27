"""Pydantic models for simulation types.

Covers simulation inputs. The runner interface types live in ``gen_1.types`` and are
re-exported here. Trial records live in ``metis.core.trials``. The specification schema
is published by metis-core. See ``packages/core/schemas/README.md``.
"""

from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from metis.core import Artifact
from metis.core.experiment import Persona, Task
from metis.core.specification import Specification as CoreSpecification
from metis.core.trials import GraderRef

from .gen_1.types import (
    ActionResult,
    ActionSlot,
    ButtonClickAction,
    ChosenAction,
    FormElement,
    FormFillAction,
    Observation,
    TrialMeta,
    UIState,
    UploadFileAction,
    UserAgentInput,
    UserAgentOutput,
)

__all__ = [
    "ActionResult",
    "ActionSlot",
    "Artifact",
    "ButtonClickAction",
    "ChosenAction",
    "FormElement",
    "FormFillAction",
    "Observation",
    "Persona",
    "Scenario",
    "Specification",
    "TrialMeta",
    "UIState",
    "UploadFileAction",
    "UserAgentInput",
    "UserAgentOutput",
]

# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


class Scenario(BaseModel):
    task_id: str = ""
    id: str
    description: str
    metadata: dict[str, str] = Field(default_factory=dict)
    num_trials: int = 1
    fixtures: list[str] = Field(default_factory=list)
    persona_refs: list[str] = Field(min_length=1)
    grader_refs: list[GraderRef] = Field(default_factory=list)
    max_turns: int = 20
    timeout_minutes: int = 15
    response_wait_ms: int = 300000
    max_trial_retries: int | None = None
    user_agent_model: str | None = None
    """The Task's ``user_agent_model``. ``None`` takes the experiment default."""

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
                        description=criterion.description,
                    )
                )
        return Scenario(
            id=scenario.id,
            task_id=task.id,
            description=scenario.description,
            metadata=scenario.metadata,
            persona_refs=[task.persona_ref],
            num_trials=task.num_trials,
            max_turns=task.max_turns,
            timeout_minutes=task.timeout_minutes,
            response_wait_ms=task.response_wait_ms,
            max_trial_retries=task.max_run_retries,
            user_agent_model=task.user_agent_model,
            fixtures=task.fixtures,
            grader_refs=refs,
        )

    @classmethod
    def load_file(cls, path: Path) -> Self:
        import yaml

        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
