"""Shared judgment shapes, output instructions, and response validation for judges."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from metis.library.grader import NonEmptyText


class BinaryJudgment(BaseModel):
    """A binary assessment, or a skipped assessment when evidence does not apply."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["scored", "skipped"]
    score: float | None = Field(strict=True)
    reason: NonEmptyText

    @model_validator(mode="after")
    def _check_score(self) -> Self:
        if self.status == "scored" and self.score not in (0.0, 1.0):
            raise ValueError("A scored result needs a binary score of 0 or 1.")
        if self.status == "skipped" and self.score is not None:
            raise ValueError("A skipped result needs a null score.")
        return self


class JudgmentShape(StrEnum):
    """Select matching output instructions and response validation for a judge."""

    BINARY = "binary"

    @property
    def response_model(self) -> type[BinaryJudgment]:
        return {JudgmentShape.BINARY: BinaryJudgment}[self]


OUTPUT_INSTRUCTIONS: dict[JudgmentShape, str] = {
    JudgmentShape.BINARY: (
        "Return status scored and score 1 if the evidence satisfies the criterion, "
        "or score 0 if it does not. Return status skipped and score null if "
        "there is no applicable evidence. Give a non-empty reason grounded in "
        "the observations."
    ),
}
