"""metis.core — Domain models, interfaces, and infrastructure."""

from importlib.metadata import PackageNotFoundError, version

from metis.core.console import console
from metis.core.logging import configure_logging, get_logger
from metis.core.models import Status

try:
    __version__ = version("metis-core")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = ["Status", "__version__", "configure_logging", "console", "get_logger"]
