"""metis.wizard — Evaluation config generator.

The names exported here are the headless package facade. Doors and providers live behind
internal modules so moving them does not change the imports used by callers.
"""

from importlib.metadata import PackageNotFoundError, version

from metis.core import Status
from metis.core import __version__ as core_version
from metis.wizard.application import Session, SessionState, SessionVersionError
from metis.wizard.application.compile import (
    CompilationError,
    compile_experiment,
    render_review,
    write_experiment,
    write_review,
)
from metis.wizard.contracts import (
    AnyRequest,
    AnyResponse,
    ProductProfile,
    UserResponse,
    WizardRequest,
)

try:
    __version__ = version("metis-wizard")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "AnyRequest",
    "AnyResponse",
    "CompilationError",
    "ProductProfile",
    "Session",
    "SessionState",
    "SessionVersionError",
    "Status",
    "UserResponse",
    "WizardRequest",
    "__version__",
    "compile_experiment",
    "core_version",
    "render_review",
    "write_experiment",
    "write_review",
]
