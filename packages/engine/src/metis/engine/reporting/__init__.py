"""Report generation (terminal, JSON, HTML)."""

from metis.engine.reporting.generator import (
    PersonaContext,
    ReportResult,
    TaskContext,
    generate_report,
)

__all__ = ["PersonaContext", "ReportResult", "TaskContext", "generate_report"]
