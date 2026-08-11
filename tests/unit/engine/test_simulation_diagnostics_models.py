"""Tests for diagnostics models added to simulation types."""

from typing import Literal

from metis.engine.simulation.types import (
    ActionRetry,
    ConversationTurn,
    RunFailure,
    RunRecord,
    TurnDiagnostics,
)


class TestActionRetry:
    def test_construct(self) -> None:
        r = ActionRetry(
            action="send_message",
            attempt=2,
            strategy_used="AriaStrategy",
            error="TimeoutError: locator timed out",
            duration_ms=1500,
        )
        assert r.action == "send_message"
        assert r.attempt == 2
        assert r.duration_ms == 1500


class TestTurnDiagnostics:
    def test_defaults(self) -> None:
        d = TurnDiagnostics()
        assert d.retry_count == 0
        assert d.failure_type is None
        assert d.submission_phase == "n/a"
        assert d.action_retries == []
        assert d.recovered is False
        assert d.recovery_found_response is None
        assert d.duration_ms == 0

    def test_with_values(self) -> None:
        d = TurnDiagnostics(
            retry_count=1,
            failure_type="transient_dom",
            submission_phase="pre",
            recovered=True,
            recovery_found_response=False,
            duration_ms=3200,
        )
        assert d.retry_count == 1
        assert d.submission_phase == "pre"


class TestRunFailure:
    def test_construct(self) -> None:
        f = RunFailure(
            attempt_number=1,
            failure_type="auth_loss",
            submission_phase="post",
            turn_reached=5,
            error_message="redirected to /login",
            duration_ms=45000,
        )
        assert f.attempt_number == 1
        assert f.failure_type == "auth_loss"
        assert f.submission_phase == "post"


class TestConversationTurnExtension:
    def test_diagnostics_defaults_to_none(self) -> None:
        turn = ConversationTurn(
            turn_number=1,
            user_message="hello",
            target_response={"text": "hi"},
            duration_ms=1000,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert turn.diagnostics is None

    def test_diagnostics_can_be_set(self) -> None:
        turn = ConversationTurn(
            turn_number=1,
            user_message="hello",
            target_response={"text": "hi"},
            duration_ms=1000,
            timestamp="2026-01-01T00:00:00Z",
            diagnostics=TurnDiagnostics(retry_count=1),
        )
        assert turn.diagnostics is not None
        assert turn.diagnostics.retry_count == 1


class TestRunRecordExtension:
    def test_new_fields_default_backward_compatible(self) -> None:
        record = RunRecord.model_validate({
            "schema_version": 2,
            "config": {
                "persona": "p",
                "scenario": "s",
            },
            "outcome": {
                "stop_reason": "max_turns",
                "total_turns": 10,
                "duration_seconds": 60.0,
            },
        })
        assert record.attempt_number == 1
        assert record.total_attempts == 1
        assert record.prior_failures == []

    def test_schema_version_is_2(self) -> None:
        record = RunRecord.model_validate({
            "schema_version": 2,
            "config": {"persona": "p", "scenario": "s"},
            "outcome": {
                "stop_reason": "max_turns",
                "total_turns": 5,
                "duration_seconds": 30.0,
            },
        })
        assert record.schema_version == 2
