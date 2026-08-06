"""Tracing remains optional, useful, and unable to break a model call."""

from __future__ import annotations

import builtins
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from metis.wizard.adapters.llm import tracing
from metis.wizard.adapters.llm.gateway import (
    API_KEY_VAR,
    BASE_URL_VAR,
    GatewayInterviewer,
    ModelOutputError,
)
from metis.wizard.application import prompts
from metis.wizard.contracts import ClarifyResult


@dataclass
class RecordingAttempt:
    attempt: int
    messages: tracing.Messages
    model: str
    finished: dict[str, Any] | None = None

    def finish(
        self,
        *,
        output: str,
        usage: tracing.UsageDetails | None,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        self.finished = {
            "output": output,
            "usage": usage,
            "latency_ms": latency_ms,
            "error": error,
        }


@dataclass
class RecordingCall:
    name: str
    model: str
    session_id: str | None
    attempts: list[RecordingAttempt] = field(default_factory=list)
    finished: bool = False

    def start_attempt(
        self, *, attempt: int, messages: tracing.Messages, model: str
    ) -> RecordingAttempt:
        record = RecordingAttempt(attempt, messages, model)
        self.attempts.append(record)
        return record

    def finish(self) -> None:
        self.finished = True


class RecordingTracer:
    def __init__(self) -> None:
        self.calls: list[RecordingCall] = []
        self.flushes = 0

    def start_call(
        self, *, name: str, model: str, session_id: str | None
    ) -> RecordingCall:
        call = RecordingCall(name, model, session_id)
        self.calls.append(call)
        return call

    def flush(self, timeout: float = tracing.FLUSH_TIMEOUT_SECONDS) -> None:
        self.flushes += 1


@dataclass
class FakeCompletions:
    replies: list[str]
    usages: list[dict[str, int] | None] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        text = self.replies[index]
        usage = self.usages[index] if self.usages is not None else None
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=usage,
        )


@dataclass
class FakeClient:
    completions: FakeCompletions

    @property
    def chat(self) -> FakeClient:
        return self


def _model(
    replies: list[str],
    tracer: tracing.Tracer,
    *,
    session_id: str | None = "wizard-test",
    usages: list[dict[str, int] | None] | None = None,
) -> tuple[GatewayInterviewer, FakeCompletions]:
    completions = FakeCompletions(replies, usages=usages)
    model = GatewayInterviewer(
        _client=FakeClient(completions),
        session_id=session_id,
        _tracer=tracer,
    )
    return model, completions


def _prompt() -> prompts.ModelPrompt:
    return prompts.ModelPrompt(
        name="clarify", system="system wording", user="user wording"
    )


@pytest.fixture(autouse=True)
def _clean_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BASE_URL_VAR, "https://gateway.example")
    monkeypatch.setenv(API_KEY_VAR, "key")
    for name in (
        tracing.LANGFUSE_BASE_URL_VAR,
        tracing.LANGFUSE_PUBLIC_KEY_VAR,
        tracing.LANGFUSE_SECRET_KEY_VAR,
    ):
        monkeypatch.delenv(name, raising=False)
    tracing.reset_tracer_cache()
    yield
    tracing.reset_tracer_cache()


def test_no_configuration_selects_noop_without_constructing_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tracing,
        "_new_backend",
        lambda configuration: pytest.fail(f"unexpected backend: {configuration}"),
    )

    tracer = tracing.get_tracer()
    tracer.start_call(name="clarify", model="model", session_id=None).finish()


def test_partial_configuration_stays_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(tracing.LANGFUSE_BASE_URL_VAR, "http://langfuse.local")
    monkeypatch.setenv(tracing.LANGFUSE_PUBLIC_KEY_VAR, "public")
    monkeypatch.setattr(
        tracing,
        "_new_backend",
        lambda configuration: pytest.fail(f"unexpected backend: {configuration}"),
    )

    tracing.get_tracer().flush()


def test_complete_configuration_builds_one_cached_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in (
        (tracing.LANGFUSE_BASE_URL_VAR, "http://langfuse.local"),
        (tracing.LANGFUSE_PUBLIC_KEY_VAR, "public"),
        (tracing.LANGFUSE_SECRET_KEY_VAR, "secret"),
    ):
        monkeypatch.setenv(name, value)
    backend = RecordingTracer()
    created: list[tuple[str, str, str]] = []
    registered: list[object] = []

    def build(configuration: tuple[str, str, str]) -> tracing.Tracer:
        created.append(configuration)
        return backend

    monkeypatch.setattr(tracing, "_new_backend", build)
    monkeypatch.setattr(tracing, "_exit_registered", False)
    monkeypatch.setattr(tracing.atexit, "register", registered.append)

    first = tracing.get_tracer()
    second = tracing.get_tracer()
    first.start_call(name="clarify", model="model", session_id="wizard-test").finish()
    second.start_call(name="clarify", model="model", session_id="wizard-test").finish()
    registered[0]()

    assert created == [("http://langfuse.local", "public", "secret")]
    assert backend.flushes == 1
    assert registered == [tracing._flush_cached]


def test_missing_optional_library_falls_back_without_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def import_without_langfuse(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "langfuse":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    original_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", import_without_langfuse)

    assert isinstance(
        tracing._new_backend(("http://langfuse.local", "public", "secret")),
        tracing.NoopTracer,
    )


def test_call_records_prompt_retries_raw_reply_usage_and_session() -> None:
    good = ClarifyResult(message="", done=True).model_dump_json()
    recorder = RecordingTracer()
    model, _ = _model(
        ["{}", good],
        recorder,
        usages=[
            {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        ],
    )

    result, recovered = model._ask(_prompt(), ClarifyResult)

    assert result.done
    assert recovered
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call.name == "clarify"
    assert call.model == model.model
    assert call.session_id == "wizard-test"
    assert call.finished
    assert len(call.attempts) == 2
    assert call.attempts[0].messages == [
        {"role": "system", "content": "system wording"},
        {"role": "user", "content": "user wording"},
    ]
    assert call.attempts[0].finished is not None
    assert call.attempts[0].finished["output"] == "{}"
    assert call.attempts[0].finished["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert call.attempts[0].finished["error"]
    assert call.attempts[0].finished["latency_ms"] >= 0
    assert call.attempts[1].messages[2] == {
        "role": "assistant",
        "content": "{}",
    }
    assert "didn't validate" in call.attempts[1].messages[3]["content"]
    assert call.attempts[1].finished is not None
    assert call.attempts[1].finished["output"] == good
    assert call.attempts[1].finished["error"] is None


def test_exhausted_call_records_all_attempts_before_raising() -> None:
    recorder = RecordingTracer()
    model, _ = _model(["{}"], recorder)

    with pytest.raises(ModelOutputError):
        model._ask(_prompt(), ClarifyResult)

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call.finished
    assert len(call.attempts) == 3
    assert all(attempt.finished is not None for attempt in call.attempts)


def test_recording_failure_does_not_change_model_result() -> None:
    class ExplodingTracer:
        def start_call(self, **kwargs: Any) -> Any:
            raise RuntimeError("trace start failed")

        def flush(self, **kwargs: Any) -> None:
            raise RuntimeError("trace flush failed")

    good = ClarifyResult(message="", done=True).model_dump_json()
    model, _ = _model([good], ExplodingTracer())  # type: ignore[arg-type]

    result, recovered = model._ask(_prompt(), ClarifyResult)

    assert result.done
    assert not recovered


def test_unconfigured_call_without_session_is_still_recordable() -> None:
    recorder = RecordingTracer()
    good = ClarifyResult(message="", done=True).model_dump_json()
    model, _ = _model([good], recorder, session_id=None)

    model._ask(_prompt(), ClarifyResult)

    assert recorder.calls[0].session_id is None
    assert recorder.calls[0].attempts[0].finished is not None


class FakeObservation:
    def __init__(self, *, as_type: str, name: str, **kwargs: Any) -> None:
        self.as_type = as_type
        self.name = name
        self.kwargs = kwargs
        self.trace_updates: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.closed = False

    def __enter__(self) -> FakeObservation:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def update_trace(self, **kwargs: Any) -> None:
        self.trace_updates.append(kwargs)

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.observations: list[FakeObservation] = []
        self.flushes = 0

    def start_as_current_observation(self, *, as_type: str, name: str, **kwargs: Any):
        observation = FakeObservation(as_type=as_type, name=name, **kwargs)
        self.observations.append(observation)

        class Context:
            def __enter__(context_self: Any) -> FakeObservation:
                return observation.__enter__()

            def __exit__(context_self: Any, *args: Any) -> None:
                observation.__exit__(*args)

        return Context()

    def flush(self) -> None:
        self.flushes += 1


def test_v3_backend_uses_root_span_and_child_generation() -> None:
    client = FakeLangfuseClient()
    tracer = tracing._LangfuseTracer(client)
    call = tracer.start_call(name="clarify", model="model", session_id="wizard-test")
    attempt = call.start_attempt(
        attempt=1,
        messages=[{"role": "user", "content": "prompt"}],
        model="model",
    )
    attempt.finish(
        output="reply",
        usage={"total_tokens": 4},
        latency_ms=12.5,
        error="validation failed",
    )
    call.finish()

    root, generation = client.observations
    assert root.as_type == "span"
    assert root.name == "clarify"
    assert root.trace_updates[0]["session_id"] == "wizard-test"
    assert generation.as_type == "generation"
    assert generation.kwargs["input"] == [{"role": "user", "content": "prompt"}]
    assert generation.updates[0]["output"] == "reply"
    assert generation.updates[0]["usage_details"] == {"total_tokens": 4}
    assert generation.updates[0]["level"] == "ERROR"
    assert root.closed
    assert generation.closed


def test_failing_flush_is_bounded_and_silent() -> None:
    class FailingClient:
        def flush(self) -> None:
            raise RuntimeError("unreachable host")

    started = time.perf_counter()
    tracing._LangfuseTracer(FailingClient()).flush(timeout=0.1)

    assert time.perf_counter() - started < 1


def test_exit_flush_contains_a_failing_backend() -> None:
    class FailingTracer:
        def flush(self, timeout: float = tracing.FLUSH_TIMEOUT_SECONDS) -> None:
            raise RuntimeError("flush failed")

    tracing._tracer_cache[("host", "public", "secret")] = FailingTracer()  # type: ignore[assignment]

    tracing._flush_cached()
