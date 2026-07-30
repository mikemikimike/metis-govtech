"""Demo metric — proves the library package wiring works. Replace with real metrics."""

from pydantic import BaseModel


class DemoMetric(BaseModel):
    """Demo metric — placeholder to validate cross-package imports. Replace with real metrics."""

    name: str = "demo"
    score: float = 1.0
