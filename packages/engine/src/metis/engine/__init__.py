"""metis.engine — Evaluation engine for METIS."""

from importlib.metadata import PackageNotFoundError, version

from metis.engine.evaluation import EvalResult, evaluate
from metis.engine.extractor import (
    FetchLangfuseResult,
    fetch_by_session_id,
    get_langfuse_client,
)
from metis.engine.reporting import ReportResult, generate_report

try:
    __version__ = version("metis-engine")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "EvalResult",
    "FetchLangfuseResult",
    "ReportResult",
    "__version__",
    "evaluate",
    "fetch_by_session_id",
    "generate_report",
    "get_langfuse_client",
]
