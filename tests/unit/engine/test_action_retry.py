"""Tests for the action retry decorator."""

import pytest

from metis.engine.simulation.exceptions import (
    AuthLossError,
    PageCrashError,
    PostSubmissionObservationError,
    TransientDOMError,
)
from metis.engine.simulation.runners.playwright._config import RetryConfig
from metis.engine.simulation.runners.playwright._retry import (
    action_retry,
    track_submission,
)


class TestActionRetry:
    @pytest.mark.asyncio
    async def test_retries_on_timeout_error(self) -> None:
        call_count = 0
        config = RetryConfig(action_max_attempts=3)

        @action_retry(config)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("locator timeout")
            return "success"

        result = await flaky()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_transient_dom_after_exhaustion(self) -> None:
        config = RetryConfig(action_max_attempts=2)

        @action_retry(config)
        async def always_fails():
            raise TimeoutError("never finds it")

        with pytest.raises(TransientDOMError):
            await always_fails()

    @pytest.mark.asyncio
    async def test_does_not_retry_auth_loss(self) -> None:
        call_count = 0
        config = RetryConfig(action_max_attempts=3)

        @action_retry(config)
        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise AuthLossError("redirected to /login")

        with pytest.raises(AuthLossError):
            await auth_fail()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_page_crash(self) -> None:
        call_count = 0
        config = RetryConfig(action_max_attempts=3)

        @action_retry(config)
        async def crash():
            nonlocal call_count
            call_count += 1
            raise PageCrashError("browser disconnected")

        with pytest.raises(PageCrashError):
            await crash()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_post_submission_failure_raises_post_submission_error(self) -> None:
        config = RetryConfig(action_max_attempts=3)

        @action_retry(config)
        async def send_with_failure():
            track_submission()
            raise TimeoutError("response capture failed")

        with pytest.raises(PostSubmissionObservationError):
            await send_with_failure()

    @pytest.mark.asyncio
    async def test_pre_submission_failure_retries_normally(self) -> None:
        call_count = 0
        config = RetryConfig(action_max_attempts=3)

        @action_retry(config)
        async def send_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("textarea not found")
            track_submission()
            return "done"

        result = await send_ok()
        assert result == "done"
        assert call_count == 2
