"""Generated-artifact collection for the Orca API runner.

A settled digest lists the files the turn generated. Each one with a
``fileId`` is streamed from ``GET /files/{fileId}/content`` into the run's
``artifacts/`` directory and reported as a ``download`` artifact whose uri is
a ``file://`` URL — the same shape the browser runner produces, so the
orchestrator, the artifact manifest and artifact-aware metrics need no
transport-specific change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from metis.core import Artifact
from metis.core.logging import get_logger

from .._http import download_to

logger = get_logger()


async def collect_artifacts(
    client: httpx.AsyncClient,
    files: list[dict[str, Any]],
    artifacts_dir: Path,
) -> tuple[list[Artifact], list[str]]:
    """Download a digest's ``files`` into ``artifacts_dir``.

    :returns: One ``download`` artifact per entry, in digest order, plus a
        note for each that could not be fetched. An entry with
        ``fileId: null`` (Orca did not store it under the key's namespace) or
        whose download fails is still recorded by name, with no url, so one
        undownloadable file never loses the turn — and never leaves a partial
        file behind.
    """
    artifacts: list[Artifact] = []
    notes: list[str] = []
    for entry in files:
        file_id = entry.get("fileId")
        name = _local_name(entry.get("name"), file_id)
        if not file_id:
            artifacts.append(Artifact(name=name, uri=None))
            notes.append(f"Artifact '{name}' is not downloadable (no fileId)")
            logger.warning("[orca-api-runner] Artifact %r has no fileId; skipped", name)
            continue

        dest = _unused_path(artifacts_dir, name)
        try:
            await download_to(client, f"files/{file_id}/content", dest)
        except httpx.HTTPError as exc:
            reason = _describe(exc)
            artifacts.append(Artifact(name=name, uri=None))
            notes.append(f"Artifact '{name}' could not be downloaded: {reason}")
            logger.warning(
                "[orca-api-runner] Artifact %r (file %s) download failed: %s",
                name,
                file_id,
                reason,
            )
            continue

        artifacts.append(Artifact(name=name, uri=Path(dest).resolve().as_uri()))
        logger.info("[orca-api-runner] Artifact %r saved to %s", name, dest)
    return artifacts, notes


def _local_name(reported: object, file_id: object) -> str:
    """The reported name stripped of any directory components."""
    raw = str(reported or file_id or "artifact")
    name = Path(raw.replace("\\", "/")).name
    return name or str(file_id or "artifact")


def _unused_path(directory: Path, name: str) -> Path:
    """``directory/name``, or ``directory/name-N.ext`` when that already exists.

    Two artifacts with the same reported name (across turns, or within one
    digest) are both kept rather than the later silently overwriting the
    earlier.
    """
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _describe(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {exc}"
