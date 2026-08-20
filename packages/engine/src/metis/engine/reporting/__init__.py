"""Report generation (terminal, JSON, HTML)."""

from metis.engine.reporting._types import (
    SessionMetricResult,
    SessionMetricsEntry,
    SessionToolCallData,
    SessionTurnData,
    TurnMetricResult,
    TurnMetricsEntry,
)
from metis.engine.reporting.generator import (
    PersonaContext,
    ReportResult,
    TaskContext,
    generate_report,
)

__all__ = [
    "PersonaContext",
    "ReportResult",
    "SessionMetricResult",
    "SessionMetricsEntry",
    "SessionToolCallData",
    "SessionTurnData",
    "TaskContext",
    "TurnMetricResult",
    "TurnMetricsEntry",
    "generate_report",
]
