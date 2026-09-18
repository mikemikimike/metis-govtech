"""Generated-artifact collection for the Orca API runner.

A settled digest lists the files the turn generated. Each one with a
``fileId`` is streamed from ``GET /files/{fileId}/content`` into the run's
``artifacts/`` directory and reported as a ``download`` artifact whose path
is a POSIX-relative string under the experiment root — the same shape the
browser runner produces, so the orchestrator, the artifact manifest and
artifact-aware metrics need no transport-specific change.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from metis.core import Artifact
from metis.core.logging import get_logger

from ...exceptions import AuthLossError
from .._http import download_to

if TYPE_CHECKING:
    from .._http import Clock, Sleep

logger = get_logger()


async def collect_artifacts(
    client: httpx.AsyncClient,
    files: list[dict[str, Any]],
    artifacts_dir: Path,
    experiment_root: Path,
    *,
    store_retry_window_s: float = 30.0,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> tuple[list[Artifact], list[str]]:
    """Download a digest's ``files`` into ``artifacts_dir``.

    Downloads sit on Orca's read lane, so each one carries the same 429 /
    503 policy as every other v1 call: a throttled lane costs a wait, not
    the file. Without that a 429 would degrade straight into permanent
    artifact loss, which is the failure this collector exists to avoid.

    :param store_retry_window_s: How long a 503 is retried before the file is
        given up on; a 429 is retried per ``Retry-After`` without a ceiling.
    :returns: One ``download`` artifact per entry, in digest order, plus a
        note for each that could not be fetched. An entry with
        ``fileId: null`` (Orca did not store it under the key's namespace) or
        whose download fails is still recorded by name, with no url, so one
        undownloadable file never loses the turn — and never leaves a partial
        file behind.
    :raises AuthLossError: on a 401. The one status that is not per-file: the
        key is gone, so every later call in the run would fail the same way.
    """
    artifacts: list[Artifact] = []
    notes: list[str] = []
    for entry in files:
        file_id = entry.get("fileId")
        name = _local_name(entry.get("name"), file_id)
        if not file_id:
            artifacts.append(Artifact(name=name, path=None))
            notes.append(f"Artifact '{name}' is not downloadable (no fileId)")
            logger.warning("[orca-api-runner] Artifact %r has no fileId; skipped", name)
            continue

        dest = _unused_path(artifacts_dir, name)
        try:
            await download_to(
                client,
                f"files/{file_id}/content",
                dest,
                unavailable_window_s=store_retry_window_s,
                clock=clock,
                sleep=sleep,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise AuthLossError(
                    "Orca rejected the API key (401) while downloading artifact "
                    f"'{name}'"
                ) from exc
            reason = _describe(exc)
            artifacts.append(Artifact(name=name, path=None))
            notes.append(f"Artifact '{name}' could not be downloaded: {reason}")
            logger.warning(
                "[orca-api-runner] Artifact %r (file %s) download failed: %s",
                name,
                file_id,
                reason,
            )
            continue
        except httpx.HTTPError as exc:
            reason = _describe(exc)
            artifacts.append(Artifact(name=name, path=None))
            notes.append(f"Artifact '{name}' could not be downloaded: {reason}")
            logger.warning(
                "[orca-api-runner] Artifact %r (file %s) download failed: %s",
                name,
                file_id,
                reason,
            )
            continue

        artifacts.append(
            Artifact(
                name=name,
                path=Path(dest)
                .resolve()
                .relative_to(experiment_root.resolve())
                .as_posix(),
            )
        )
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
