"""Report generation (terminal, JSON, HTML)."""

from metis.engine.reporting._types import (
    PersonaContext,
    SessionMetricResult,
    SessionReport,
    TaskContext,
    TurnMetricResult,
    TurnReport,
)
from metis.engine.reporting.generator import (
    ReportResult,
    generate_report,
)

__all__ = [
    "PersonaContext",
    "ReportResult",
    "SessionMetricResult",
    "SessionReport",
    "TaskContext",
    "TurnMetricResult",
    "TurnReport",
    "generate_report",
]
