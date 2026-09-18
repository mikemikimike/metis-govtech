"""Fixture upload for the Orca API runner: each file reaches Orca's library once.

Orca's ``POST /files`` stores a file under the key's namespace and returns a
``fileId`` that any later turn in any session may attach, so an experiment
uploads each fixture at most once: the :class:`FixtureLibrary` is owned by
the runner factory, shared by every runner of the experiment, and keyed by
the fixture name the scenario references. Uploads sit on Orca's submit lane
and so go through the experiment's shared limiter. A fixture Orca refuses
(413 too large, 415 content type not accepted) is refused for the whole
experiment too — the reason is cached so a 25 MiB file is not re-sent on
every run only to be rejected again.
"""

from __future__ import annotations

import asyncio
import mimetypes
from typing import TYPE_CHECKING

from metis.core.logging import get_logger

from ._transport import reason_text, v1_request

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

    from .._http import Clock, Sleep, SubmitRateLimiter

logger = get_logger()

#: Content types Orca accepts by default, keyed by suffix. Pinned here rather
#: than left to ``mimetypes`` so the declared type (what Orca checks) does not
#: depend on the evaluator's OS registry; anything else falls back to a guess.
_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

_FALLBACK_CONTENT_TYPE = "application/octet-stream"


class FixtureRejected(Exception):
    """Orca refused the fixture at upload time; nothing was stored.

    Permanent for this file under the deployment's limits (size, content
    type), so it is reported to the evaluator — who can fix the experiment —
    rather than retried.
    """

    def __init__(self, name: str, status: int, reason: str) -> None:
        super().__init__(f"File '{name}' rejected by Orca ({status}): {reason}")
        self.name = name
        self.status = status
        self.reason = reason


class FixtureLibrary:
    """Experiment-scoped ``name → fileId`` cache over ``POST /files``.

    :param limiter: The experiment's submit-lane pacer; every upload waits on it.
    :param clock: / :param sleep: Injected by tests so retry waits are instant.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        limiter: SubmitRateLimiter,
        *,
        store_retry_window_s: float,
        clock: Clock,
        sleep: Sleep,
    ) -> None:
        self._client = client
        self._limiter = limiter
        self._store_retry_window_s = store_retry_window_s
        self._clock = clock
        self._sleep = sleep
        self._entries: dict[str, str | FixtureRejected] = {}
        # One lock per name: concurrent runners racing for the same fixture
        # wait for the first upload instead of each starting their own.
        self._locks: dict[str, asyncio.Lock] = {}

    async def file_id(self, name: str, path: Path) -> str:
        """The ``fileId`` of fixture ``name``, uploading ``path`` on first use.

        :raises FixtureRejected: Orca refused the file (413 / 415); the same
            rejection is raised again for every later request of that name.
        :raises httpx.HTTPStatusError: any other non-2xx upload response.
        """
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            cached = self._entries.get(name)
            if isinstance(cached, FixtureRejected):
                raise cached
            if cached is not None:
                return cached
            try:
                file_id = await self._upload(name, path)
            except FixtureRejected as exc:
                self._entries[name] = exc
                raise
            self._entries[name] = file_id
            return file_id

    def forget(self, name: str) -> bool:
        """Drop a cached ``fileId`` so the next request re-uploads the fixture.

        For an id Orca no longer honours — a file deleted, or expired 30 days
        after *upload* rather than after last use, which a long-lived
        experiment directory outlives. Without this the cache is
        experiment-scoped, so one dead id is re-sent on every run of every
        scenario that attaches it, and every one of those submits fails.

        A cached :class:`FixtureRejected` is left in place: that rejection is
        a property of the file (too large, wrong content type), not of an id,
        and re-uploading could only earn it again.

        :returns: Whether a usable ``fileId`` was cached under ``name``.
        """
        if isinstance(self._entries.get(name), str):
            del self._entries[name]
            logger.info(
                "[orca-api-runner] Forgot cached fileId for fixture %r; "
                "it will be re-uploaded on next use",
                name,
            )
            return True
        return False

    async def _upload(self, name: str, path: Path) -> str:
        content_type = content_type_for(path)
        content = await asyncio.to_thread(path.read_bytes)
        logger.info(
            "[orca-api-runner] Uploading fixture %r (%s, %d bytes)",
            name,
            content_type,
            len(content),
        )
        response = await v1_request(
            self._client,
            "POST",
            "files",
            files={"file": (path.name, content, content_type)},
            limiter=self._limiter,
            submit=True,
            store_retry_window_s=self._store_retry_window_s,
            clock=self._clock,
            sleep=self._sleep,
        )
        if response.status_code in (413, 415):
            raise FixtureRejected(name, response.status_code, reason_text(response))
        response.raise_for_status()
        file_id = str(response.json()["fileId"])
        logger.info("[orca-api-runner] Fixture %r stored as file %s", name, file_id)
        return file_id


def content_type_for(path: Path) -> str:
    """The multipart ``Content-Type`` to declare for a fixture (what Orca checks)."""
    known = _CONTENT_TYPES.get(path.suffix.lower())
    if known:
        return known
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or _FALLBACK_CONTENT_TYPE
