"""Tests for shared HTTP utilities in runners/_http.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from metis.engine.simulation.runners._http import (
    PollTimeout,
    SubmitRateLimiter,
    download_to,
    poll_until,
    retry_after_seconds,
    send_with_backoff,
)


class TestPollUntil:
    @pytest.mark.asyncio
    async def test_returns_immediately_when_settled(self) -> None:
        result = await poll_until(
            AsyncMock(return_value={"status": "done"}),
            lambda d: d["status"] == "done",
            interval_s=1.0,
            deadline_s=5.0,
        )
        assert result == {"status": "done"}

    @pytest.mark.asyncio
    async def test_polls_until_settled(self) -> None:
        responses = iter(
            [{"status": "running"}, {"status": "running"}, {"status": "done"}]
        )
        fetch = AsyncMock(side_effect=lambda: next(responses))
        result = await poll_until(
            fetch,
            lambda d: d["status"] == "done",
            interval_s=0.01,
            deadline_s=5.0,
        )
        assert result == {"status": "done"}
        assert fetch.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_poll_timeout(self) -> None:
        with pytest.raises(PollTimeout):
            await poll_until(
                AsyncMock(return_value={"status": "running"}),
                lambda d: d["status"] == "done",
                interval_s=0.01,
                deadline_s=0.05,
            )


class TestSubmitRateLimiter:
    @pytest.mark.asyncio
    async def test_spaces_calls(self) -> None:
        now = 0.0

        def clock() -> float:
            return now

        async def sleep(s: float) -> None:
            nonlocal now
            now += s

        limiter = SubmitRateLimiter(6, clock=clock, sleep=sleep)
        await limiter.acquire()
        first_slot = now
        await limiter.acquire()
        assert now - first_slot == pytest.approx(10.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_rpm_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="rpm must be >= 1"):
            SubmitRateLimiter(0)


class TestRetryAfterSeconds:
    def test_parses_delay_seconds(self) -> None:
        resp = MagicMock()
        resp.headers = {"Retry-After": "30"}
        assert retry_after_seconds(resp, 5.0) == 30.0

    def test_missing_header_returns_default(self) -> None:
        resp = MagicMock()
        resp.headers = {}
        assert retry_after_seconds(resp, 5.0) == 5.0

    def test_negative_clamps_to_zero(self) -> None:
        resp = MagicMock()
        resp.headers = {"Retry-After": "-1"}
        assert retry_after_seconds(resp, 5.0) == 0.0


def _fake_response(
    status: int, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status, headers=headers or {})


class TestSendWithBackoff:
    @pytest.mark.asyncio
    async def test_returns_success_immediately(self) -> None:
        send = AsyncMock(return_value=_fake_response(200))
        result = await send_with_backoff(send, unavailable_window_s=10)
        assert result.status_code == 200
        assert send.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_429_with_retry_after(self) -> None:
        now = 0.0

        def clock() -> float:
            return now

        async def sleep(s: float) -> None:
            nonlocal now
            now += s

        responses = iter(
            [
                _fake_response(429, {"Retry-After": "2"}),
                _fake_response(200),
            ]
        )
        send = AsyncMock(side_effect=lambda: next(responses))
        result = await send_with_backoff(
            send, unavailable_window_s=10, clock=clock, sleep=sleep
        )
        assert result.status_code == 200
        assert send.call_count == 2
        assert now == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_retries_429_uses_default_when_no_header(self) -> None:
        now = 0.0

        def clock() -> float:
            return now

        async def sleep(s: float) -> None:
            nonlocal now
            now += s

        responses = iter([_fake_response(429), _fake_response(200)])
        send = AsyncMock(side_effect=lambda: next(responses))
        result = await send_with_backoff(
            send,
            unavailable_window_s=10,
            retry_after_default_s=3.0,
            clock=clock,
            sleep=sleep,
        )
        assert result.status_code == 200
        assert now == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_503_retries_with_backoff_then_returns(self) -> None:
        now = 0.0

        def clock() -> float:
            return now

        async def sleep(s: float) -> None:
            nonlocal now
            now += s

        send = AsyncMock(return_value=_fake_response(503))
        result = await send_with_backoff(
            send,
            unavailable_window_s=5,
            unavailable_backoff_s=1.0,
            clock=clock,
            sleep=sleep,
        )
        assert result.status_code == 503
        assert send.call_count >= 3

    @pytest.mark.asyncio
    async def test_503_recovers_before_deadline(self) -> None:
        now = 0.0

        def clock() -> float:
            return now

        async def sleep(s: float) -> None:
            nonlocal now
            now += s

        responses = iter(
            [_fake_response(503), _fake_response(503), _fake_response(200)]
        )
        send = AsyncMock(side_effect=lambda: next(responses))
        result = await send_with_backoff(
            send,
            unavailable_window_s=30,
            unavailable_backoff_s=1.0,
            clock=clock,
            sleep=sleep,
        )
        assert result.status_code == 200
        assert send.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_status_returned_immediately(self) -> None:
        send = AsyncMock(return_value=_fake_response(401))
        result = await send_with_backoff(send, unavailable_window_s=10)
        assert result.status_code == 401
        assert send.call_count == 1


class TestDownloadTo:
    @pytest.mark.asyncio
    async def test_downloads_to_dest(self, tmp_path: Path) -> None:
        dest = tmp_path / "subdir" / "file.txt"
        content = b"hello world"

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=content)
        )
        client = httpx.AsyncClient(transport=transport)

        await download_to(client, "http://example.com/file", dest)

        assert dest.exists()
        assert dest.read_bytes() == content
        assert not dest.with_name(f".{dest.name}.part").exists()

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        dest = tmp_path / "a" / "b" / "c" / "file.bin"

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=b"data")
        )
        client = httpx.AsyncClient(transport=transport)

        await download_to(client, "http://example.com/file", dest)
        assert dest.exists()

    @pytest.mark.asyncio
    async def test_cleans_up_partial_on_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "file.txt"

        transport = httpx.MockTransport(lambda req: httpx.Response(500))
        client = httpx.AsyncClient(transport=transport)

        with pytest.raises(httpx.HTTPStatusError):
            await download_to(client, "http://example.com/file", dest)

        assert not dest.exists()
        assert not dest.with_name(f".{dest.name}.part").exists()
