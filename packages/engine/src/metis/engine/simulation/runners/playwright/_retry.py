"""Retry decorator for DOM actions with point-of-no-return tracking."""

from __future__ import annotations

import asyncio
import contextvars
import functools
from typing import TYPE_CHECKING, Any

from metis.engine.simulation.exceptions import (
    AuthLossError,
    PageCrashError,
    PostSubmissionObservationError,
    ResponseTimeoutError,
    TransientDOMError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from ._config import RetryConfig

_submission_committed: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_submission_committed", default=False
)


def track_submission() -> None:
    """Mark that an irreversible submission has occurred in the current action call.

    After this call, any exception will be raised as PostSubmissionObservationError
    instead of being retried.
    """
    _submission_committed.set(True)


def action_retry(
    config: RetryConfig,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, Any]]],
    Callable[..., Coroutine[Any, Any, Any]],
]:
    """Decorator factory for retrying async DOM actions with exponential backoff.

    - Retries on any exception not in the no-retry set.
    - If the wrapped function raises after ``track_submission()`` was called,
      raises ``PostSubmissionObservationError`` immediately (no retry).
    - ``AuthLossError``, ``PageCrashError``, and ``PostSubmissionObservationError``
      are never retried — they propagate immediately.
    - After exhausting all attempts, raises ``TransientDOMError``.
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = _submission_committed.set(False)
            attempts = 0
            last_error: Exception | None = None

            try:
                while attempts < config.action_max_attempts:
                    attempts += 1
                    try:
                        return await func(*args, **kwargs)
                    except (
                        AuthLossError,
                        PageCrashError,
                        PostSubmissionObservationError,
                        ResponseTimeoutError,
                    ):
                        raise
                    except Exception as exc:
                        if _submission_committed.get():
                            raise PostSubmissionObservationError(str(exc)) from exc
                        last_error = exc
                        if attempts >= config.action_max_attempts:
                            break
                        delay = min(
                            config.action_backoff_base_seconds * (2 ** (attempts - 1)),
                            config.action_backoff_max_seconds,
                        )
                        await asyncio.sleep(delay)

                raise TransientDOMError(str(last_error)) from last_error
            finally:
                _submission_committed.reset(token)

        return wrapper

    return decorator
