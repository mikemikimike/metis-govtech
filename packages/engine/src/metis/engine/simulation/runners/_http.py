"""HTTP utilities shared by API-driven runners.

Small functions, not a base class: a runner for another platform composes the
pieces it needs without inheriting Orca's protocol shape.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

import httpx

T = TypeVar("T")

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


def build_client(
    base_url: str,
    api_key: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_s: float = 30.0,
    insecure: bool = False,
) -> httpx.AsyncClient:
    """An async client rooted at ``base_url`` that sends ``Authorization: Bearer``.

    :param transport: Injected by tests to serve an in-process fake server; the
        default opens real connections.
    """
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/") + "/",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_s,
        transport=transport,
        verify=not insecure,
    )


class PollTimeout(Exception):
    """``poll_until`` reached its deadline before the condition held."""


async def poll_until(
    fetch: Callable[[], Awaitable[T]],
    is_settled: Callable[[T], bool],
    *,
    interval_s: float,
    deadline_s: float,
) -> T:
    """Call ``fetch`` every ``interval_s`` until ``is_settled(result)`` is true.

    The first fetch happens immediately; the deadline is checked after each
    unsettled result, so a poll is never started once ``deadline_s`` has
    elapsed and the final sleep is clipped to the time remaining.

    :raises PollTimeout: if the result is still unsettled at the deadline.
    """
    deadline = time.monotonic() + deadline_s
    while True:
        result = await fetch()
        if is_settled(result):
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PollTimeout(f"still unsettled after {deadline_s:.1f}s")
        await asyncio.sleep(min(interval_s, remaining))


class SubmitRateLimiter:
    """Paces calls on a rate-limited lane shared by every runner of one experiment.

    Grants are spaced evenly at ``window_s / rpm`` seconds rather than allowing
    bursts: at most ``rpm`` grants fall inside *any* rolling window, wherever the
    server's own window happens to start, and concurrent workers interleave in
    arrival order instead of racing. The cost is that the first ``rpm`` calls
    of an experiment are paced too, which Orca's turn latency dwarfs.

    :param rpm: Grants per ``window_s``; Orca's submit lane default is 6.
    :param clock: ``time.monotonic``-like; injected by tests with a fake clock.
    :param sleep: ``asyncio.sleep``-like; must advance ``clock`` when faked.
    """

    def __init__(
        self,
        rpm: int,
        *,
        window_s: float = 60.0,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rpm < 1:
            raise ValueError(f"rpm must be >= 1, got {rpm}")
        #: Seconds between consecutive grants.
        self.interval_s = window_s / rpm
        self._clock = clock
        self._sleep = sleep
        self._next_slot: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Return once a call may be sent; send immediately afterwards."""
        async with self._lock:
            now = self._clock()
            if self._next_slot is not None:
                # Loop, not a single sleep: a timer may wake a hair early.
                while now < self._next_slot:
                    await self._sleep(self._next_slot - now)
                    now = self._clock()
            self._next_slot = now + self.interval_s

    async def __aenter__(self) -> SubmitRateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


def retry_after_seconds(response: httpx.Response, default_s: float) -> float:
    """Seconds to wait per a ``Retry-After`` header in its delay-seconds form.

    A missing, blank or HTTP-date value yields ``default_s``; a negative value
    clamps to zero.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return default_s
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        return default_s


async def send_with_backoff(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    unavailable_window_s: float,
    retry_after_default_s: float = 1.0,
    unavailable_backoff_s: float = 1.0,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> httpx.Response:
    """Call ``send`` until it returns something other than a 429 or a 503.

    - **429** — wait ``Retry-After`` (``retry_after_default_s`` when the header
      is absent) and send again. The server said when to come back, so this
      never gives up on its own.
    - **503** — wait ``unavailable_backoff_s``, doubling each time, for at most
      ``unavailable_window_s`` after the first 503 (the final sleep is clipped
      to the window). Once the window is spent the last 503 is *returned* for
      the caller to map onto its own failure type.

    Every other response, error statuses included, is returned untouched. Each
    attempt is a fresh ``send()`` call, so whatever pacing or auth ``send``
    applies is applied to retries too.
    """
    deadline: float | None = None
    backoff = unavailable_backoff_s
    while True:
        response = await send()
        if response.status_code == 429:
            await sleep(retry_after_seconds(response, retry_after_default_s))
            continue
        if response.status_code == 503:
            now = clock()
            if deadline is None:
                deadline = now + unavailable_window_s
            remaining = deadline - now
            if remaining <= 0:
                return response
            await sleep(min(backoff, remaining))
            backoff *= 2
            continue
        return response


async def download_to(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    chunk_size: int = 64 * 1024,
) -> None:
    """Stream ``GET url`` into ``dest`` without buffering the body in memory.

    Bytes go to a ``.part`` sibling that is renamed over ``dest`` only once the
    whole body has arrived, so ``dest`` is either complete or absent — a
    failed or interrupted download never leaves a partial file behind.
    Parent directories are created as needed.

    :raises httpx.HTTPStatusError: on a non-2xx response (before any write).
    :raises httpx.HTTPError: on a transport failure, including mid-stream.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(f".{dest.name}.part")
    try:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                async for chunk in response.aiter_bytes(chunk_size):
                    out.write(chunk)
        partial.replace(dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
