"""v1_request maps httpx transport errors onto a recoverable exception."""

from __future__ import annotations

import time

import httpx
import pytest

from metis.engine.simulation.exceptions import TargetUnavailableError
from metis.engine.simulation.runners._http import SubmitRateLimiter
from metis.engine.simulation.runners.orca_api._transport import v1_request


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_transport_error_becomes_target_unavailable() -> None:
    """A connection/read error on a v1 call raises TargetUnavailableError
    (turn-recoverable) instead of a bare, message-less httpx exception."""

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure", request=request)

    client = httpx.AsyncClient(
        base_url="http://orca.test/api/v1/",
        transport=httpx.MockTransport(_boom),
    )
    limiter = SubmitRateLimiter(6)
    try:
        with pytest.raises(TargetUnavailableError) as excinfo:
            await v1_request(
                client,
                "GET",
                "chat/turn-123",
                limiter=limiter,
                store_retry_window_s=1.0,
                clock=time.monotonic,
                sleep=_no_sleep,
            )
        # The mapped error is descriptive, not blank.
        assert "GET chat/turn-123" in str(excinfo.value)
        assert "ConnectError" in str(excinfo.value)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_read_timeout_becomes_target_unavailable() -> None:
    """A read timeout — the empty-message case from issue #250 — is mapped too."""

    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)

    client = httpx.AsyncClient(
        base_url="http://orca.test/api/v1/",
        transport=httpx.MockTransport(_timeout),
    )
    limiter = SubmitRateLimiter(6)
    try:
        with pytest.raises(TargetUnavailableError) as excinfo:
            await v1_request(
                client,
                "GET",
                "chat/turn-123",
                limiter=limiter,
                store_retry_window_s=1.0,
                clock=time.monotonic,
                sleep=_no_sleep,
            )
        # The mapped error is descriptive despite empty source message.
        assert "ReadTimeout" in str(excinfo.value)
        assert "Transport error" in str(excinfo.value)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_successful_request_still_returns_response() -> None:
    """The happy path is unchanged: a 200 is returned untouched."""

    client = httpx.AsyncClient(
        base_url="http://orca.test/api/v1/",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": 1})),
    )
    limiter = SubmitRateLimiter(6)
    try:
        response = await v1_request(
            client,
            "GET",
            "chat/turn-123",
            limiter=limiter,
            store_retry_window_s=1.0,
            clock=time.monotonic,
            sleep=_no_sleep,
        )
        assert response.status_code == 200
    finally:
        await client.aclose()
