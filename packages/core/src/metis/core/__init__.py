"""metis.core — Domain models, interfaces, and infrastructure."""

from importlib.metadata import PackageNotFoundError, version

from metis.core.artifacts import Artifact, resolve_artifact_path
from metis.core.console import console
from metis.core.logging import configure_logging, get_logger
from metis.core.models import Status
from metis.core.traces import GradingInput, Observation, Trace

try:
    __version__ = version("metis-core")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "Artifact",
    "GradingInput",
    "Observation",
    "Status",
    "Trace",
    "__version__",
    "configure_logging",
    "console",
    "get_logger",
    "resolve_artifact_path",
]
