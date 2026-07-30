"""metis.engine — Evaluation runtime."""

from importlib.metadata import PackageNotFoundError, version

from metis.core import Status
from metis.core import __version__ as core_version
from metis.library import DemoMetric

try:
    __version__ = version("metis-engine")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = ["DemoMetric", "Status", "__version__", "core_version"]
