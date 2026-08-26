"""Report generation (terminal summary and the product evaluation report)."""

from metis.engine.reporting._report import build_report, load_report_sources
from metis.engine.reporting._types import (
    SessionMetricResult,
    SessionReport,
    TurnMetricResult,
    TurnReport,
)
from metis.engine.reporting.generator import (
    ReportResult,
    generate_report,
    save_report,
)

__all__ = [
    "ReportResult",
    "SessionMetricResult",
    "SessionReport",
    "TurnMetricResult",
    "TurnReport",
    "build_report",
    "generate_report",
    "load_report_sources",
    "save_report",
]
