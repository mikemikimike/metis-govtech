"""What the wizard reads from the grader library.

Design-time metadata only. The wizard never instantiates a grader and never runs one — which
is also why the catalogue is built from class names and docstrings rather than from
instances: many graders take constructor arguments, and instantiating one just to read its
display name would be the wizard doing exactly what it says it never does.
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
    fqn: str  # "metis.library.graders.TurnBudgetGrader"
    name: str  # "Turn budget" — what the user sees
    description: str
    # Constructor defaults seed the Criterion parameters for user review.
    params: list[GraderParam] = Field(default_factory=list)

    @property
    def match_text(self) -> str:
        """What the matcher embeds for this grader."""
        return f"{self.name}. {self.description}"


class GraderSummary(BaseModel):
    """The small, stable grader shape exposed to presentation clients."""

    fqn: str
    name: str
    description: str
