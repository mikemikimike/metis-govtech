"""Internal types for browser interaction state.

Canonical definitions live in simulation/types.py; re-exported here for
backwards compatibility within the harness package.
"""

from ..types import Artifact, FormElement, UIState

__all__ = ["Artifact", "FormElement", "UIState"]
