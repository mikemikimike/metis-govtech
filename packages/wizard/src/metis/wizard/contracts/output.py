"""Structured-output targets — what the model is asked to return, and nothing more.

These are not persisted. A `StepResult` is applied to the profile and discarded; what
survives is the profile it changed and the transcript line it produced.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from metis.wizard.contracts.conversation import Option
from metis.wizard.domain.patch import Patch
from metis.wizard.domain.profile import Behaviour, Criterion, Epic, Persona, Task


class ClarifyResult(BaseModel):
    """The clarify loop is the only place the model decides when to stop.

    Everywhere else a step ends on a user action, because everywhere else something gets
    committed. The `done` flag is advisory even here — a hard turn cap overrides it, because
    a mediocre first draft is recoverable on the very next screen and an interview that never
    ends is not.
    """

    done: bool
    question: str | None = None


class StepResultEpic(Epic):
    """An epic drafted by the model must contain the behaviours it is introducing."""

    behaviours: list[Behaviour] = Field(min_length=1)


class StepResultPatch(Patch):
    """A model-facing patch whose value shape is visible to structured output.

    Runtime patches stay generic because their value depends on their path. The model needs
    a finite union, though, or a provider can satisfy the schema by turning nested objects
    into strings. This covers every value a model-owned address accepts.
    """

    value: (
        StepResultEpic
        | Behaviour
        | Criterion
        | Persona
        | Task
        | str
        | int
        | bool
        | list[str]
        | None
    ) = None

    @model_validator(mode="before")
    @classmethod
    def from_runtime_patch(cls, value: object) -> object:
        """Keep scripted and package callers that already construct `Patch` working."""
        if isinstance(value, Patch) and not isinstance(value, cls):
            return value.model_dump(mode="python")
        return value


class StepResult(BaseModel):
    """What every step other than clarify returns.

    `patches` are addressed edits; `options` are suggestion chips, each already carrying the
    patch that applies it, so clicking one costs no second model call.
    """

    message: str
    patches: list[StepResultPatch] = Field(default_factory=list)
    options: list[Option] = Field(default_factory=list)
