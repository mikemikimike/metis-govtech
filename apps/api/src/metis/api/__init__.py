"""metis.api — REST API service (Phase 4)."""

from importlib.metadata import PackageNotFoundError, version

from metis.core import Status
from metis.core import __version__ as core_version

try:
    __version__ = version("metis-api")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = ["Status", "__version__", "core_version"]
