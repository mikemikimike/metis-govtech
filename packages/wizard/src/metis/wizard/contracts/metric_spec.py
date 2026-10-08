"""What the wizard reads from the metric library.

Design-time metadata only. The wizard never instantiates a metric and never runs one — which
is also why the catalogue is built from class names and docstrings rather than from
instances: many metrics take constructor arguments, and instantiating one just to read its
display name would be the wizard doing exactly what it says it never does.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricParam(BaseModel):
    name: str
    type: str
    default: Any = None
    required: bool = False


class MetricSpec(BaseModel):
    fqn: str  # "metis.library.metrics.TurnBudgetMetric"
    name: str  # "Turn budget" — what the user sees
    description: str
    # Constructor defaults seed the Criterion parameters for user review.
    params: list[MetricParam] = Field(default_factory=list)

    @property
    def match_text(self) -> str:
        """What the matcher embeds for this metric."""
        return f"{self.name}. {self.description}"


class MetricSummary(BaseModel):
    """The small, stable metric shape exposed to presentation clients."""

    fqn: str
    name: str
    description: str
