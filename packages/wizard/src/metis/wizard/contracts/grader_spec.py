"""What the wizard reads from the grader library.

Design-time metadata only. The wizard never instantiates a grader and never runs one — which
is also why the catalogue is built from class names and docstrings rather than from
instances: a grader's parameters are its `args_model` fields, which are read from the class.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraderParam(BaseModel):
    name: str
    type: str
    default: Any = None
    required: bool = False


class GraderSpec(BaseModel):
    fqn: str  # "metis.library.graders.demo.DemoTraceBudgetGrader"
    name: str  # "Turn budget" — what the user sees
    description: str
    # args_model fields seed the Criterion parameters for user review.
    params: list[GraderParam] = Field(default_factory=list)
    # The grader takes its instructions from the criterion description, so it fits any
    # criterion and is never a similarity match.
    uses_criterion_description: bool = False

    @property
    def match_text(self) -> str:
        """What the matcher embeds for this grader."""
        return f"{self.name}. {self.description}"


class GraderSummary(BaseModel):
    """The small, stable grader shape exposed to presentation clients."""

    fqn: str
    name: str
    description: str
    uses_criterion_description: bool = False
