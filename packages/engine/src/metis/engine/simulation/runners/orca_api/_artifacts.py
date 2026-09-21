"""Generated-artifact collection for the Orca API runner.

A settled digest lists the files the turn generated, and ``GET /sessions/{id}``
lists the cumulative set — which is strictly larger, because the digest omits
Vega-Lite chart specs (issue #337). Each entry with a ``fileId`` not already
held is streamed from ``GET /files/{fileId}/content`` into the run's
``artifacts/`` directory and reported as a ``download`` artifact whose path
is a POSIX-relative string under the experiment root — the same shape the
browser runner produces, so the orchestrator, the artifact manifest and
artifact-aware metrics need no transport-specific change.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import httpx

from metis.core import Artifact
from metis.core.logging import get_logger

from ...exceptions import AuthLossError
from .._http import download_to

if TYPE_CHECKING:
    from .._http import Clock, Sleep

logger = get_logger()


class ArtifactNote(NamedTuple):
    """A per-file diagnostic and the file identity it belongs to, kept apart.

    The two fields have different audiences, which is the whole point of the
    type. ``text`` is persona-visible: ``send_turn`` copies it into
    ``Observation.errors``, which is rendered into the simulated user's prompt.
    ``file_id`` is the runner's own bookkeeping and must never reach that
    prompt — a real user of a chat product is never shown a backend file id,
    and ``Observation.errors`` is not a diagnostics channel (see
    :meth:`OrcaApiRunner._reconcile_session_artifacts`).

    The id has to travel alongside the text because
    :func:`reconcile_by_identity` has to drop the note about a file another
    lane went on to recover, and a **name is not an identity**. Orca reuses
    names by design — a revision arrives as a new ``fileId`` under the same
    name, which lands beside its sibling as ``analysis_script-2.py`` — so
    matching on the name erases an unrelated entry's only diagnostic and
    leaves its ``path=None`` artifact unexplained, the exact silent loss issue
    #337 exists to end.

    ``file_id`` is ``None`` for an entry Orca never stored under the key's
    namespace, which has no identity to reconcile on.
    """

    text: str
    file_id: str | None = None


async def collect_artifacts(
    client: httpx.AsyncClient,
    files: list[dict[str, Any]],
    artifacts_dir: Path,
    experiment_root: Path,
    *,
    seen_file_ids: set[str] | None = None,
    store_retry_window_s: float = 30.0,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> tuple[list[Artifact], list[ArtifactNote]]:
    """Download a digest's ``files`` into ``artifacts_dir``.

    Downloads sit on Orca's read lane, so each one carries the same 429 /
    503 policy as every other v1 call: a throttled lane costs a wait, not
    the file. Without that a 429 would degrade straight into permanent
    artifact loss, which is the failure this collector exists to avoid.

    :param seen_file_ids: ``fileId``s already downloaded in this run. An entry
        whose id is present is skipped and omitted from the result, and every
        successful download adds its id. Orca files are immutable, so the same
        id is always the same bytes and a re-listed entry is pure duplication —
        while a *revised* document arrives under a new id and is still kept,
        renamed by :func:`_unused_path`. Omit it to download every entry, which
        is the historical behaviour.
    :param store_retry_window_s: How long a 503 is retried before the file is
        given up on; a 429 is retried per ``Retry-After`` without a ceiling.
    :returns: One ``download`` artifact per entry not already held (see
        ``seen_file_ids``), in digest order, plus an :class:`ArtifactNote` for
        each that could not be fetched, carrying the file's id out of band so
        the note can later be matched to the file by identity. Each artifact
        carries the
        entry's ``fileId`` as ``external_id`` — including the ones that failed
        to download, so a later re-check can retry exactly those. An entry with
        ``fileId: null`` (Orca did not store it under the key's namespace) or
        whose download fails is still recorded by name, with no url, so one
        undownloadable file never loses the turn — and never leaves a partial
        file behind.
    :raises AuthLossError: on a 401. The one status that is not per-file: the
        key is gone, so every later call in the run would fail the same way.
    """
    artifacts: list[Artifact] = []
    notes: list[ArtifactNote] = []
    for entry in files:
        file_id = entry.get("fileId")
        name = _local_name(entry.get("name"), file_id)
        if not file_id:
            artifacts.append(Artifact(name=name, path=None))
            notes.append(
                ArtifactNote(f"Artifact '{name}' is not downloadable (no fileId)")
            )
            logger.warning("[orca-api-runner] Artifact %r has no fileId; skipped", name)
            continue

        if seen_file_ids is not None and str(file_id) in seen_file_ids:
            logger.debug(
                "[orca-api-runner] Artifact %r (file %s) already held; skipped",
                name,
                file_id,
            )
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
            artifacts.append(Artifact(name=name, path=None, external_id=str(file_id)))
            notes.append(
                ArtifactNote(
                    f"Artifact '{name}' could not be downloaded: {reason}",
                    str(file_id),
                )
            )
            logger.warning(
                "[orca-api-runner] Artifact %r (file %s) download failed: %s",
                name,
                file_id,
                reason,
            )
            continue
        except httpx.HTTPError as exc:
            reason = _describe(exc)
            artifacts.append(Artifact(name=name, path=None, external_id=str(file_id)))
            notes.append(
                ArtifactNote(
                    f"Artifact '{name}' could not be downloaded: {reason}",
                    str(file_id),
                )
            )
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
                external_id=str(file_id),
                path=Path(dest)
                .resolve()
                .relative_to(experiment_root.resolve())
                .as_posix(),
            )
        )
        if seen_file_ids is not None:
            seen_file_ids.add(str(file_id))
        logger.info("[orca-api-runner] Artifact %r saved to %s", name, dest)
    return artifacts, notes


async def collect_session_artifacts(
    client: httpx.AsyncClient,
    session_files: list[dict[str, Any]],
    artifacts_dir: Path,
    experiment_root: Path,
    *,
    seen_file_ids: set[str],
    store_retry_window_s: float = 30.0,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> tuple[list[Artifact], list[ArtifactNote]]:
    """Download ``source="generated"`` session files not already held.

    The turn digest under-reports: ``TurnDigest.files`` excludes Vega-Lite
    chart specs that ``GET /sessions/{id}`` lists as generated with working
    ``fileId``s. This is the net that catches them, so the loss stops being
    silent whatever the digest omits next.

    ``source="uploaded"`` entries are skipped: a fixture is already recorded
    as a ``source="fixture"`` artifact by ``send_turn``, and re-downloading the
    persona's own input as a target deliverable would be a fidelity error, not
    a recovery.

    :param seen_file_ids: Required here, unlike in :func:`collect_artifacts`.
        ``Session.files`` is cumulative for the whole session, so without
        identity dedupe a per-turn sweep re-downloads every file every turn
        and :func:`_unused_path` fans them out as ``-2``, ``-3``, and so on.
    :returns: The same ``(artifacts, notes)`` shape as
        :func:`collect_artifacts`, empty when there is nothing to recover.
        Recovered artifacts carry no turn attribution of their own —
        ``Session.files`` has none — so a file generated on turn 2 but first
        surfaced here on turn 3 is attributed to turn 3. A generated entry with
        no ``fileId`` is unrecoverable and is warned about rather than recorded:
        it has no identity, so an artifact minted here would be a second phantom
        beside the one the digest lane already records for the same file.
    """
    missing: list[dict[str, Any]] = []
    skipped_non_dict = 0
    skipped_no_id: list[str] = []
    skipped_source: list[str] = []
    for entry in session_files:
        if not isinstance(entry, dict):
            skipped_non_dict += 1
            continue
        source = entry.get("source")
        if source == "uploaded":
            continue  # documented exclusion: fixture already recorded by send_turn
        if source != "generated":
            skipped_source.append(str(source))
            continue
        if not entry.get("fileId"):
            skipped_no_id.append(_local_name(entry.get("name"), None))
            continue
        if str(entry["fileId"]) in seen_file_ids:
            continue
        missing.append(entry)

    if skipped_non_dict:
        logger.debug(
            "[orca-api-runner] Session file list: %d non-dict entr%s skipped",
            skipped_non_dict,
            "ies" if skipped_non_dict != 1 else "y",
        )
    if skipped_no_id:
        # A generated file Orca listed but will not serve, and nothing
        # downstream can recover it. An entry with no fileId has no identity, so
        # the sweep cannot tell whether the digest lane reported this same file:
        # when the digest omitted it too, this line is the run's only trace of
        # it, and the silent drop it replaces is the loss #337 exists to end.
        # That missing identity is equally why nothing is recorded here — an
        # artifact minted for it would reconcile against nothing and stand as a
        # second phantom beside the digest lane's. Warning rather than debug
        # because, unlike the two cases below, this is a file going missing and
        # not a shape METIS declines to read; log-only because
        # Observation.errors is the persona's prompt, not a diagnostics channel.
        logger.warning(
            "[orca-api-runner] Session lists %d generated file(s) with no fileId; "
            "unrecoverable and absent from the run: %s",
            len(skipped_no_id),
            ", ".join(repr(n) for n in skipped_no_id[:5]),
        )
    if skipped_source:
        # debug, not info: the sweep runs every turn, so a deployment that adds
        # a third source would otherwise print one line per turn per run for a
        # fact that is the same every time.
        logger.debug(
            "[orca-api-runner] Session file list: %d entr%s with unrecognised "
            "source skipped (expected 'generated' or 'uploaded'); sources: %s",
            len(skipped_source),
            "ies" if len(skipped_source) != 1 else "y",
            ", ".join(repr(s) for s in skipped_source[:5]),
        )

    if not missing:
        return [], []
    logger.info(
        "[orca-api-runner] Session lists %d generated file(s) the digest omitted; "
        "recovering",
        len(missing),
    )
    return await collect_artifacts(
        client,
        missing,
        artifacts_dir,
        experiment_root,
        seen_file_ids=seen_file_ids,
        store_retry_window_s=store_retry_window_s,
        clock=clock,
        sleep=sleep,
    )


def reconcile_by_identity(
    artifacts: list[Artifact], notes: list[ArtifactNote]
) -> tuple[list[Artifact], list[ArtifactNote]]:
    """Collapse the two collection lanes into one record per file identity.

    Both lanes can report the same ``fileId`` within one turn: the sweep's
    candidate filter excludes only ids already *held*, and a failed download
    deliberately does not mark its id as held (it must stay retryable), so a
    file the digest lane could not fetch is attempted again by the sweep. Both
    outcomes then arrive here, and exactly one of them may survive:

    - **one lane succeeded** — the path-bearing artifact wins and the other
      lane's "could not be downloaded" note goes with the placeholder it
      described, so the record never carries a contradictory pair;
    - **both failed** — one placeholder and one note, not two of each. Every
      non-fixture artifact is rendered to the persona as a delivered file under
      a header asserting the list is everything it has received, so a
      persistently failing download would otherwise inject two phantom
      deliverables per turn and overstate what METIS holds.

    ``external_id is None`` is **not** an identity — Orca did not store that
    entry under the key's namespace, and two such entries are legitimately
    distinct files — so they are passed through untouched and never collapsed
    together, even when they share a name. Their notes carry no ``file_id``
    and are likewise always kept.

    :param artifacts: Both lanes concatenated, digest lane first.
    :param notes: Their notes, in the same order.
    :returns: ``(artifacts, notes)`` with one entry per identified file,
        preserving first-seen order.
    """
    # Where each id's surviving artifact sits, so a later winner replaces its
    # predecessor in place and the original ordering is kept.
    slot: dict[str, int] = {}
    merged: list[Artifact] = []
    for artifact in artifacts:
        file_id = artifact.external_id
        if file_id is None:
            merged.append(artifact)
            continue
        index = slot.get(file_id)
        if index is None:
            slot[file_id] = len(merged)
            merged.append(artifact)
            continue
        if merged[index].name != artifact.name:
            # Two names under one id breaks the uniqueness contract documented
            # on Artifact.external_id: a file does not rename itself while
            # keeping its id. Collapsing them loses a file silently, so name
            # the cause here — this log line is the only trace of it.
            logger.warning(
                "[orca_api] fileId %s claimed by two names (%s, %s) — the target "
                "may be reusing ids across files; they will be merged and one lost",
                file_id,
                merged[index].name,
                artifact.name,
            )
        if merged[index].path is None and artifact.path is not None:
            merged[index] = artifact

    # A file that arrived needs no diagnostic; one that did not needs exactly
    # one, however many lanes tried for it. An unidentified note, or one about
    # a file no artifact was recorded for, has nothing to reconcile against and
    # is always kept — dropping it would be the silent loss #337 exists to end.
    explained: set[str] = set()
    kept_notes: list[ArtifactNote] = []
    for note in notes:
        index = slot.get(note.file_id) if note.file_id is not None else None
        if note.file_id is None or index is None:
            kept_notes.append(note)
            continue
        if merged[index].path is not None or note.file_id in explained:
            continue
        explained.add(note.file_id)
        kept_notes.append(note)
    return merged, kept_notes


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
