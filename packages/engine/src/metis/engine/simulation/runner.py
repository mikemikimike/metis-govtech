"""Old import path; re-exports gen_1's ``Runner`` and the shared ``RunnerFactory``."""

from .factory import RunnerFactory
from .gen_1.runner import Runner

__all__ = ["Runner", "RunnerFactory"]
