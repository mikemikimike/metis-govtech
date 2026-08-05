"""Structured-output targets for the model boundary.

The draft models in this module are deliberately not the persisted profile models.  They are
the small set of semantic fields the model is allowed to propose; application code supplies
ids, authorship, defaults and matcher-owned fields afterwards.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from metis.wizard.domain.patch import Patch, PatchOp


class _StrictDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BehaviourDraft(_StrictDraft):
    statement: str


class EpicDraft(_StrictDraft):
    name: str
    behaviours: list[BehaviourDraft] = Field(min_length=1)


class CriterionDraft(_StrictDraft):
    given: str
    when: str
    then: str


class PersonaDraft(_StrictDraft):
    label: str
    description: str


class TaskDraft(_StrictDraft):
    description: str
    behaviour_refs: list[str]
    persona_refs: list[str]


_DRAFT_TYPES = (EpicDraft, BehaviourDraft, CriterionDraft, PersonaDraft, TaskDraft)


def _container(path: str) -> str:
    """Return the final collection field in a patch path."""
    return (
        re.split(r"[.\[]", path)[-1] if path.endswith("]") else path.rsplit(".", 1)[-1]
    )


def _legacy_value(path: str, value: Any) -> Any:
    """Adapt package-authored scripted patches without weakening provider JSON validation."""
    if not isinstance(value, dict):
        return value
    field = _container(path)
    if field == "epics":
        behaviours = [
            BehaviourDraft(statement=item["statement"])
            for item in value.get("behaviours", [])
        ]
        return EpicDraft(name=value["name"], behaviours=behaviours)
    if field == "behaviours":
        return BehaviourDraft(statement=value["statement"])
    if field == "criteria":
        return CriterionDraft(
            given=value["given"], when=value["when"], then=value["then"]
        )
    if field == "personas":
        return PersonaDraft(
            label=value.get("label", value.get("id", "persona")),
            description=value["description"],
        )
    if field == "tasks":
        return TaskDraft(
            description=value["description"],
            behaviour_refs=value.get("behaviour_refs", []),
            persona_refs=value.get("persona_refs", []),
        )
    return value


class StepResultPatch(BaseModel):
    """An operation-aware, model-only patch contract.

    Unlike runtime :class:`Patch`, this type has no trust marker and no generic ``Any`` value.  The
    provider must return one of the strict drafts for creation or a scalar/reference value for
    targeted edits.
    """

    model_config = ConfigDict(extra="forbid")

    op: PatchOp
    path: str
    value: (
        EpicDraft
        | BehaviourDraft
        | CriterionDraft
        | PersonaDraft
        | TaskDraft
        | str
        | int
        | bool
        | list[str]
        | None
    ) = None

    @model_validator(mode="before")
    @classmethod
    def from_runtime_patch(cls, value: object) -> object:
        # ScriptedInterviewer and wizard-owned tests construct runtime patches directly.  This
        # compatibility path is never used for provider JSON, where extra fields are rejected.
        if isinstance(value, Patch):
            data = value.model_dump(mode="python")
            data.pop("origin", None)
            data["value"] = _legacy_value(data["path"], data.get("value"))
            return data
        return value

    @model_validator(mode="after")
    def enforce_operation_shape(self) -> StepResultPatch:
        if self.op is PatchOp.ADD:
            field = self.path.rsplit(".", 1)[-1]
            expected = {
                "epics": EpicDraft,
                "behaviours": BehaviourDraft,
                "criteria": CriterionDraft,
                "personas": PersonaDraft,
                "tasks": TaskDraft,
            }.get(field)
            if expected is None or not isinstance(self.value, expected):
                raise ValueError(f"add to {field!r} requires its strict draft")
        elif isinstance(self.value, _DRAFT_TYPES):
            raise ValueError("strict drafts are only valid for add operations")
        return self


class ClarifyResult(BaseModel):
    done: bool
    question: str | None = None


class StepResult(BaseModel):
    """What every step other than clarify returns."""

    model_config = ConfigDict(extra="forbid")

    message: str
    patches: list[StepResultPatch] = Field(default_factory=list)
