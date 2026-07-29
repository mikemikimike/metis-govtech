"""metis.wizard — Evaluation config generator."""

from importlib.metadata import PackageNotFoundError, version

from metis.core import __version__ as core_version  # noqa: F401

try:
    __version__ = version("metis-wizard")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"
