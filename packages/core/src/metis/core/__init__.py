"""metis.core — Domain models, interfaces, and infrastructure."""

from importlib.metadata import PackageNotFoundError, version

from metis.core.models import Status

try:
    __version__ = version("metis-core")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = ["Status", "__version__"]
