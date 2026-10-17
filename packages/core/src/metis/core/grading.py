"""What a grader returns, and what the orchestrator records from it.

A grader reaches a verdict by returning a ``score`` in [0, 1]; it never decides pass or fail.
The orchestrator applies the criterion's threshold and stores a ``RecordedResult``, so every
grader follows the same rule and a grader cannot return an outcome that contradicts its score.

``skipped`` means the session had nothing for this grader to judge, and is never a pass.
``errored`` means the grader could not reach a verdict (a grader LLM call failed after its
retries, or its reply could not be parsed); an error says something about the grader, not the
target, so it is never a fail. Both are left out of pass rates and averages and reported
separately.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class GraderResult(BaseModel):
    """What a grader reports for one grading scope."""

    status: Literal["scored", "skipped", "errored"]
    score: float | None = Field(default=None, ge=0, le=1)
    """In [0, 1] when ``status`` is ``"scored"``; always ``None`` otherwise."""
    reason: str

    @model_validator(mode="after")
    def _score_matches_status(self) -> Self:
        if self.status == "scored" and self.score is None:
            raise ValueError("a scored result needs a score")
        if self.status != "scored" and self.score is not None:
            raise ValueError(f"a {self.status} result must not carry a score")
        return self


class GradingOutput(BaseModel):
    """What one grader run returns: one result per grading scope.

    A grader with nothing to judge returns one skipped result, never ``[]``. The orchestrator
    enforces that, replacing an empty output with a single errored result.
    """

    results: list[GraderResult]


class RecordedResult(BaseModel):
    """One ``GraderResult`` after the orchestrator has applied the threshold."""

    outcome: Literal["passed", "failed", "skipped", "errored"]
    score: float | None = Field(default=None, ge=0, le=1)
    """Set for passed and failed; ``None`` for skipped and errored."""
    reason: str

    @model_validator(mode="after")
    def _score_matches_outcome(self) -> Self:
        verdict = self.outcome in ("passed", "failed")
        if verdict and self.score is None:
            raise ValueError(f"a {self.outcome} result needs a score")
        if not verdict and self.score is not None:
            raise ValueError(f"a {self.outcome} result must not carry a score")
        return self
