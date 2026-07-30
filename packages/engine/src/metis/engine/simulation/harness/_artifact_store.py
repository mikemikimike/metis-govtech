"""Artifact persistence — copies artifacts to registry and writes manifest."""

import json
from datetime import UTC, datetime
from pathlib import Path

from ..types import SessionRecord

_TYPE_MAP = {
    "pdf": "report",
    "html": "report",
    "png": "chart",
    "jpg": "chart",
    "jpeg": "chart",
    "svg": "chart",
    "pptx": "slide_deck",
    "ppt": "slide_deck",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "csv": "data",
    "json": "data",
}


def infer_artifact_type(filename: str) -> str:
    """Infer the artifact type from a filename based on its extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _TYPE_MAP.get(ext, "unknown")


def _save_artifacts(record: SessionRecord, session_dir: Path) -> dict:
    """Write an artifact manifest for a completed simulation session.

    Artifacts are already on disk at their collected paths (written live during
    simulation). This function records them in a manifest file and returns the
    manifest dict.

    :param record: The completed session record.
    :param session_dir: The session folder (``sessions/<task>-<persona>-<uuid>/``).
    :returns: The manifest dict (also written to ``session_dir/artifacts/session-manifest.json``).
    """
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    manifest_artifacts = []
    for artifact in record.artifacts_collected:
        filename = artifact.filename or Path(artifact.path).name
        manifest_artifacts.append(
            {
                "filename": filename,
                "type": infer_artifact_type(filename),
                "collected_at_turn": artifact.collected_at_turn,
                "path": artifact.path,
            }
        )

    manifest = {
        "session_id": record.target_session_id or "",
        "persona": record.config.persona,
        "task": record.config.task,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "stop_reason": record.outcome.stop_reason,
        "artifacts": manifest_artifacts,
    }

    manifest_path = artifacts_dir / "session-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return manifest
