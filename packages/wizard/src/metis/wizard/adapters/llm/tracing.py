"""Optional Python SDK v3 tracing for a Langfuse server v3 deployment.

This module is the only wizard module that imports Langfuse. The rest of the adapter talks to the
small tracer interface below, which is also implemented by the no-op tracer. Every boundary to
the optional SDK is guarded so observability cannot change the interview.
"""

from __future__ import annotations

import atexit
import os
import threading
from typing import Any, Protocol

LANGFUSE_BASE_URL_VAR = "LANGFUSE_BASE_URL"
LANGFUSE_PUBLIC_KEY_VAR = "LANGFUSE_PUBLIC_KEY"
LANGFUSE_SECRET_KEY_VAR = "LANGFUSE_SECRET_KEY"

FLUSH_TIMEOUT_SECONDS = 2.0

Messages = list[dict[str, str]]
UsageDetails = dict[str, int]


def usage_details_from_response(response: Any) -> UsageDetails | None:
    """Extract the OpenAI-compatible token counts without retaining the SDK response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    values: UsageDetails = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = (
            usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        )
        if isinstance(value, int):
            values[name] = value
    return values or None


class AttemptTrace(Protocol):
    """The part of a trace owned by one provider attempt."""

    def finish(
        self,
        *,
        output: str,
        usage: UsageDetails | None,
        latency_ms: float,
        error: str | None = None,
    ) -> None: ...


class CallTrace(Protocol):
    """The trace for one semantic gateway call."""

    def start_attempt(
        self, *, attempt: int, messages: Messages, model: str
    ) -> AttemptTrace: ...

    def finish(self) -> None: ...


class Tracer(Protocol):
    """The tracer surface used by ``GatewayInterviewer._ask``."""

    def start_call(
        self, *, name: str, model: str, session_id: str | None
    ) -> CallTrace: ...

    def flush(self, timeout: float = FLUSH_TIMEOUT_SECONDS) -> None: ...


class _NoopAttempt:
    def finish(
        self,
        *,
        output: str,
        usage: UsageDetails | None,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        return None


class _NoopCall:
    def start_attempt(
        self, *, attempt: int, messages: Messages, model: str
    ) -> AttemptTrace:
        return _NoopAttempt()

    def finish(self) -> None:
        return None


class NoopTracer:
    """A tracer with no side effects when Langfuse is absent or disabled."""

    def start_call(self, *, name: str, model: str, session_id: str | None) -> CallTrace:
        return _NoopCall()

    def flush(self, timeout: float = FLUSH_TIMEOUT_SECONDS) -> None:
        return None


class _SafeAttempt:
    def __init__(self, inner: AttemptTrace) -> None:
        self._inner = inner

    def finish(
        self,
        *,
        output: str,
        usage: UsageDetails | None,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        try:
            self._inner.finish(
                output=output,
                usage=usage,
                latency_ms=latency_ms,
                error=error,
            )
        except Exception:
            # Tracing is diagnostic. A broken exporter must not reach the interview.
            return None


class _SafeCall:
    def __init__(self, inner: CallTrace) -> None:
        self._inner = inner

    def start_attempt(
        self, *, attempt: int, messages: Messages, model: str
    ) -> AttemptTrace:
        try:
            return _SafeAttempt(
                self._inner.start_attempt(
                    attempt=attempt, messages=messages, model=model
                )
            )
        except Exception:
            return _NoopAttempt()

    def finish(self) -> None:
        try:
            self._inner.finish()
        except Exception:
            return None


class _SafeTracer:
    """Contain failures from both the real tracer and injected test doubles."""

    def __init__(self, inner: Tracer) -> None:
        self._inner = inner

    def start_call(self, *, name: str, model: str, session_id: str | None) -> CallTrace:
        try:
            return _SafeCall(
                self._inner.start_call(name=name, model=model, session_id=session_id)
            )
        except Exception:
            return _SafeCall(_NoopCall())

    def flush(self, timeout: float = FLUSH_TIMEOUT_SECONDS) -> None:
        try:
            self._inner.flush(timeout=timeout)
        except Exception:
            return None


class _LangfuseAttempt:
    def __init__(self, context: Any, generation: Any) -> None:
        self._context = context
        self._generation = generation
        self._closed = False

    def finish(
        self,
        *,
        output: str,
        usage: UsageDetails | None,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        if self._closed:
            return

        try:
            metadata: dict[str, Any] = {"latency_ms": round(latency_ms, 3)}
            if error is not None:
                metadata["validation_error"] = error
            updates: dict[str, Any] = {
                "output": output,
                "metadata": metadata,
            }
            if usage:
                updates["usage_details"] = usage
            if error is not None:
                updates["level"] = "ERROR"
                updates["status_message"] = error
            self._generation.update(**updates)
        finally:
            self._close()

    def _close(self) -> None:
        if not self._closed:
            self._closed = True
            self._context.__exit__(None, None, None)


class _LangfuseCall:
    def __init__(self, context: Any, root: Any, client: Any) -> None:
        self._context = context
        self._root = root
        self._client = client
        self._closed = False

    def start_attempt(
        self, *, attempt: int, messages: Messages, model: str
    ) -> AttemptTrace:
        context = self._client.start_as_current_observation(
            as_type="generation",
            name=f"attempt-{attempt}",
            model=model,
            input=messages,
        )
        generation = context.__enter__()
        return _LangfuseAttempt(context, generation)

    def finish(self) -> None:
        if not self._closed:
            self._closed = True
            self._context.__exit__(None, None, None)


class _LangfuseTracer:
    def __init__(self, client: Any) -> None:
        self._client = client

    def start_call(self, *, name: str, model: str, session_id: str | None) -> CallTrace:
        context = self._client.start_as_current_observation(as_type="span", name=name)
        root = context.__enter__()
        try:
            trace_metadata = {"step": name, "model": model}
            update: dict[str, Any] = {
                "name": name,
                "metadata": trace_metadata,
            }
            if session_id:
                update["session_id"] = session_id
            root.update_trace(**update)
        except Exception:
            # Keep the root observation alive even if optional trace attributes fail.
            pass
        return _LangfuseCall(context, root, self._client)

    def flush(self, timeout: float = FLUSH_TIMEOUT_SECONDS) -> None:
        finished = threading.Event()

        def _flush() -> None:
            try:
                try:
                    self._client.flush()
                except Exception:
                    return None
            finally:
                finished.set()

        thread = threading.Thread(target=_flush, daemon=True)
        thread.start()
        finished.wait(timeout=max(0.0, timeout))


_cache_lock = threading.Lock()
_tracer_cache: dict[tuple[str, str, str], Tracer] = {}
_exit_registered = False


def _configuration() -> tuple[str, str, str] | None:
    base_url = os.environ.get(LANGFUSE_BASE_URL_VAR, "").strip()
    public_key = os.environ.get(LANGFUSE_PUBLIC_KEY_VAR, "").strip()
    secret_key = os.environ.get(LANGFUSE_SECRET_KEY_VAR, "").strip()
    if not all((base_url, public_key, secret_key)):
        return None
    return base_url, public_key, secret_key


def _new_backend(configuration: tuple[str, str, str]) -> Tracer:
    try:
        from langfuse import Langfuse

        client = Langfuse(
            host=configuration[0],
            public_key=configuration[1],
            secret_key=configuration[2],
        )
    except Exception:
        return NoopTracer()
    return _LangfuseTracer(client)


def _flush_cached() -> None:
    with _cache_lock:
        tracers = tuple(_tracer_cache.values())
    for tracer in tracers:
        try:
            tracer.flush()
        except Exception:
            # The exit hook must never turn an observability failure into an exit failure.
            continue


def get_tracer() -> Tracer:
    """Return a safe tracer selected from the current optional configuration."""
    global _exit_registered

    try:
        configuration = _configuration()
        if configuration is None:
            return _SafeTracer(NoopTracer())

        with _cache_lock:
            tracer = _tracer_cache.get(configuration)
            if tracer is None:
                tracer = _new_backend(configuration)
                _tracer_cache[configuration] = tracer
            if not _exit_registered:
                atexit.register(_flush_cached)
                _exit_registered = True
        return _SafeTracer(tracer)
    except Exception:
        # Configuration and process-exit registration are outside the model call too, but they
        # must still be unable to stop the wizard from starting.
        return _SafeTracer(NoopTracer())


def make_safe_tracer(tracer: Tracer) -> Tracer:
    """Wrap a supplied tracer so tests and custom adapters get the same containment."""
    return _SafeTracer(tracer)


def reset_tracer_cache() -> None:
    """Clear cached clients for isolated configuration tests."""
    with _cache_lock:
        _tracer_cache.clear()


__all__ = [
    "FLUSH_TIMEOUT_SECONDS",
    "LANGFUSE_BASE_URL_VAR",
    "LANGFUSE_PUBLIC_KEY_VAR",
    "LANGFUSE_SECRET_KEY_VAR",
    "Messages",
    "NoopTracer",
    "Tracer",
    "UsageDetails",
    "get_tracer",
    "make_safe_tracer",
    "reset_tracer_cache",
    "usage_details_from_response",
]
