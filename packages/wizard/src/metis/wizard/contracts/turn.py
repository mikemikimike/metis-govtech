"""Public typed Interview-operation and compilation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

from metis.wizard.contracts.conversation import AnyResponse
from metis.wizard.contracts.interview_state import InterviewState, Perspective
from metis.wizard.domain.permissions import InterviewStep


class InterviewStartRequest(BaseModel):
    """The first operation, containing the user's raw product description."""

    model_config = ConfigDict(extra="forbid")

    description: str
    perspective: Perspective = Perspective.END_USER

    @field_validator("description")
    @classmethod
    def _require_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value


class _InterviewStateRequest(BaseModel):
    """Shared required state for operations after start."""

    model_config = ConfigDict(extra="forbid")

    state: InterviewState


class InterviewTurnRequest(_InterviewStateRequest):
    """Answer the one pending request with its typed response."""

    request_id: str
    response: AnyResponse


class InterviewEndRequest(_InterviewStateRequest):
    """Run best-effort completion for the supplied client-held state."""


InterviewRequest: TypeAlias = (
    InterviewStartRequest | InterviewTurnRequest | InterviewEndRequest
)


class InterviewErrorCode(StrEnum):
    """Stable failure codes exposed by the in-process and HTTP interfaces."""

    NO_PENDING_REQUEST = "no_pending_request"
    REQUEST_ID_MISMATCH = "request_id_mismatch"
    RESPONSE_TYPE_MISMATCH = "response_type_mismatch"
    RESPONSE_NOT_OFFERED = "response_not_offered"
    MODEL_UNAVAILABLE = "model_unavailable"
    COMPLETION_FAILED = "completion_failed"
    INTERNAL_ERROR = "internal_error"


class MissingDataCode(StrEnum):
    """Stable codes for gaps that stop a Profile from being runnable."""

    PRODUCT_INCOMPLETE = "product_incomplete"
    BEHAVIOURS_INCOMPLETE = "behaviours_incomplete"
    NO_MEASURED_BEHAVIOUR = "no_measured_behaviour"
    CRITERIA_INCOMPLETE = "criteria_incomplete"
    NO_PERSONAS = "no_personas"
    NO_SCENARIOS = "no_scenarios"
    BEHAVIOUR_UNCOVERED = "behaviour_uncovered"
    SCENARIO_NO_SELECTED_BEHAVIOUR = "scenario_no_selected_behaviour"
    SCENARIO_NO_PERSONA = "scenario_no_persona"
    SCENARIO_UNKNOWN_REFERENCE = "scenario_unknown_reference"
    SCENARIO_INVALID_TRIALS = "scenario_invalid_trials"


class MissingData(BaseModel):
    """One structured reason a Profile is not yet runnable."""

    code: MissingDataCode
    stage: InterviewStep
    subject: str | None = None
    message: str


InterviewOutcome: TypeAlias = Literal["awaiting_response", "done"]


class InterviewSuccess(BaseModel):
    """A successful start, turn, or end operation."""

    type: Literal["success"] = "success"
    state: InterviewState
    stage: InterviewStep
    missing: list[MissingData] = Field(default_factory=list)
    outcome: InterviewOutcome


class InterviewFailure(BaseModel):
    """A typed failure with unchanged state when a safe retry state exists."""

    type: Literal["failure"] = "failure"
    code: InterviewErrorCode
    message: str
    retryable: bool
    state: InterviewState | None = None
    missing: list[MissingData] = Field(default_factory=list)


InterviewResult: TypeAlias = Annotated[
    InterviewSuccess | InterviewFailure,
    Field(discriminator="type"),
]


class CompileResult(BaseModel):
    """The two YAML strings returned by compilation, keyed by their file names."""

    model_config = ConfigDict(populate_by_name=True)

    profile_yaml: str = Field(alias="profile.yaml")
    experiment_yaml: str = Field(alias="experiment.yaml")


__all__ = [
    "CompileResult",
    "InterviewEndRequest",
    "InterviewErrorCode",
    "InterviewFailure",
    "InterviewOutcome",
    "InterviewRequest",
    "InterviewResult",
    "InterviewStartRequest",
    "InterviewSuccess",
    "InterviewTurnRequest",
    "MissingData",
    "MissingDataCode",
]
