"""One resilient ``/api/v1`` call — the piece the runner and the fixture library share.

Pacing, ``Retry-After`` and key-store backoff are applied here, and the two
lane-wide statuses are mapped onto the transport-agnostic exceptions; every
other response is returned for the caller to map.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...exceptions import AuthLossError, TargetUnavailableError
from .._http import send_with_backoff

if TYPE_CHECKING:
    import httpx

    from .._http import Clock, Sleep, SubmitRateLimiter


async def v1_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: Any | None = None,
    files: Any | None = None,
    limiter: SubmitRateLimiter,
    submit: bool = False,
    store_retry_window_s: float,
    clock: Clock,
    sleep: Sleep,
) -> httpx.Response:
    """One v1 call with the shared resilience applied; maps the lane-wide statuses.

    ``submit=True`` marks a submit-lane call (``POST /chat``, ``POST /files``):
    every attempt, retries included, waits for ``limiter`` first, so a retry
    after a 429 is still spaced against the other workers' submits rather
    than racing them. 429 and 503 are retried by :func:`send_with_backoff`; a
    503 that outlasts ``store_retry_window_s`` raises
    :class:`TargetUnavailableError` (turn-recoverable); a 401 raises
    :class:`AuthLossError` (run-level).

    :param files: An httpx ``files=`` mapping for a multipart upload; give the
        content as bytes so a retried attempt re-sends the same body.
    """

    async def send() -> httpx.Response:
        if submit:
            await limiter.acquire()
        return await client.request(method, path, json=json, files=files)

    response = await send_with_backoff(
        send,
        unavailable_window_s=store_retry_window_s,
        retry_after_default_s=limiter.interval_s,
        clock=clock,
        sleep=sleep,
    )
    if response.status_code == 401:
        raise AuthLossError("Orca rejected the API key (401)")
    if response.status_code == 503:
        raise TargetUnavailableError(
            "Orca key store unavailable (503) for longer than "
            f"{store_retry_window_s:g} s"
        )
    return response
