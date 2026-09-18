"""One resilient ``/api/v1`` call — the piece the runner and the fixture library share.

Pacing, ``Retry-After`` and key-store backoff are applied here, and the two
lane-wide statuses are mapped onto the transport-agnostic exceptions; every
other response is returned for the caller to map.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from ...exceptions import AuthLossError, TargetUnavailableError
from .._http import send_with_backoff

if TYPE_CHECKING:
    from .._http import Clock, Sleep, SubmitRateLimiter


async def v1_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: Any | None = None,
    files: Any | None = None,
    headers: dict[str, str] | None = None,
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
    :param headers: Per-request headers merged over the client's own — for a
        header that belongs to one route rather than the whole session, such
        as ``X-PlatformAI-Key`` on ``POST /chat``. Applied inside ``send`` so
        a retried attempt carries it too.
    """

    async def send() -> httpx.Response:
        if submit:
            await limiter.acquire()
        return await client.request(
            method, path, json=json, files=files, headers=headers
        )

    try:
        response = await send_with_backoff(
            send,
            unavailable_window_s=store_retry_window_s,
            retry_after_default_s=limiter.interval_s,
            clock=clock,
            sleep=sleep,
        )
    except httpx.TransportError as exc:
        # A timeout, dropped connection, or protocol error on the wire.
        # httpx timeout errors often carry an empty message; surface a
        # descriptive, turn-recoverable error instead of letting a bare,
        # message-less Exception escape and be recorded as a silent
        # system_error (see issue #250).
        raise TargetUnavailableError(
            f"Transport error on {method} {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if response.status_code == 401:
        raise AuthLossError("Orca rejected the API key (401)")
    if response.status_code == 503:
        raise TargetUnavailableError(
            "Orca key store unavailable (503) for longer than "
            f"{store_retry_window_s:g} s"
        )
    return response


def reason_text(response: httpx.Response) -> str:
    """Orca's human-readable message (``detail`` / ``error``), or its status text.

    Every v1 error body is one of these shapes, so both the fixture upload and
    the turn submit report a rejection with the server's own wording rather
    than a bare status code.
    """
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in ("detail", "error"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    text = response.text.strip()
    return text[:200] if text else response.reason_phrase or "no reason given"
