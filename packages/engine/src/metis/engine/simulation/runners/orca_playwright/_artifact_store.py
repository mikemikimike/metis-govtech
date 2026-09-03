"""Re-export from shared location for backward compatibility."""

from __future__ import annotations

from ..._artifact_store import _save_artifacts, infer_artifact_type

__all__ = ["_save_artifacts", "infer_artifact_type"]
