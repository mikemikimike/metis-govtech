"""Integration tests for the full resilience stack."""

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.exceptions import (
    AuthLossError,
    ConsecutiveFailureEscalation,
    PageCrashError,
    PostSubmissionObservationError,
    ResponseTimeoutError,
    RunRecoverableError,
    SimulationError,
    TransientDOMError,
    TurnRecoverableError,
)
from metis.engine.simulation.runners.orca_playwright._config import (
    OrcaPlaywrightRunnerConfig,
)
from metis.engine.simulation.runners.orca_playwright._element_resolver import (
    resolve_element,
)
from metis.engine.simulation.runners.orca_playwright._retry import (
    action_retry,
    track_submission,
)
from metis.engine.simulation.types import (
    ActionRetry,
    ConversationTurn,
    RunRecord,
    TurnDiagnostics,
)


class TestFullImportGraph:
    """Verify all new modules are importable without circular deps."""

    def test_exceptions_importable(self) -> None:
        from metis.engine.simulation import exceptions

        assert hasattr(exceptions, "SimulationError")
        assert hasattr(exceptions, "TransientDOMError")
        assert hasattr(exceptions, "PostSubmissionObservationError")
        assert hasattr(exceptions, "AuthLossError")
        assert hasattr(exceptions, "PageCrashError")
        assert hasattr(exceptions, "ConsecutiveFailureEscalation")
        assert hasattr(exceptions, "ResponseTimeoutError")

    def test_element_resolver_importable(self) -> None:

        assert resolve_element is not None

    def test_retry_importable(self) -> None:

        assert action_retry is not None
        assert track_submission is not None

    def test_no_circular_imports(self) -> None:
        """Importing orchestrator and runner should not fail due to circular deps."""
        import importlib

        importlib.reload(
            importlib.import_module("metis.engine.simulation.orchestrator")
        )
        importlib.reload(
            importlib.import_module("metis.engine.simulation.runners.orca_playwright")
        )


class TestExceptionCatchPatterns:
    """Verify exception hierarchy works for the catch patterns in the spec."""

    def test_turn_layer_catches_transient_dom(self) -> None:
        try:
            raise TransientDOMError("element not found")
        except TurnRecoverableError:
            pass  # correct — turn layer catches this

    def test_turn_layer_catches_post_submission(self) -> None:
        try:
            raise PostSubmissionObservationError("capture failed")
        except TurnRecoverableError:
            pass  # correct

    def test_run_layer_catches_auth_loss(self) -> None:
        try:
            raise AuthLossError("redirected")
        except RunRecoverableError:
            pass  # correct

    def test_run_layer_catches_page_crash(self) -> None:
        try:
            raise PageCrashError("disconnected")
        except RunRecoverableError:
            pass  # correct

    def test_run_layer_catches_escalation(self) -> None:
        try:
            raise ConsecutiveFailureEscalation("3 failures")
        except RunRecoverableError:
            pass  # correct

    def test_response_timeout_not_caught_by_turn_or_run(self) -> None:
        with pytest.raises(ResponseTimeoutError):
            try:
                raise ResponseTimeoutError("polling expired")
            except (TurnRecoverableError, RunRecoverableError):
                pytest.fail("Should not be caught by these handlers")

    def test_all_are_simulation_errors(self) -> None:
        for exc_class in [
            TransientDOMError,
            PostSubmissionObservationError,
            AuthLossError,
            PageCrashError,
            ConsecutiveFailureEscalation,
            ResponseTimeoutError,
        ]:
            assert issubclass(exc_class, SimulationError)


class TestDiagnosticsWiring:
    """Verify diagnostics models integrate with RunRecord correctly."""

    def test_full_run_record_with_diagnostics(self) -> None:
        turn = ConversationTurn(
            turn_number=1,
            user_message="hello",
            target_response={"text": "hi"},
            duration_ms=2000,
            timestamp="2026-01-01T00:00:00Z",
            diagnostics=TurnDiagnostics(
                retry_count=1,
                failure_type="transient_dom",
                submission_phase="pre",
                action_retries=[
                    ActionRetry(
                        action="send_message",
                        attempt=1,
                        strategy_used="CSSStrategy",
                        error="timeout",
                        duration_ms=1000,
                    )
                ],
                recovered=True,
                recovery_found_response=None,
                duration_ms=3000,
            ),
        )

        record = RunRecord.model_validate(
            {
                "schema_version": 2,
                "config": {"persona": "p", "scenario": "s"},
                "outcome": {
                    "stop_reason": "max_turns",
                    "total_turns": 1,
                    "duration_seconds": 3.0,
                },
                "conversation": [turn.model_dump()],
                "attempt_number": 2,
                "max_allowed_attempts": 3,
                "prior_failures": [
                    {
                        "attempt_number": 1,
                        "failure_type": "auth_loss",
                        "turn_reached": 5,
                        "error_message": "redirected",
                        "duration_ms": 20000,
                    }
                ],
            }
        )

        assert record.conversation[0].diagnostics is not None
        assert record.conversation[0].diagnostics.retry_count == 1
        assert len(record.prior_failures) == 1
        assert record.attempt_number == 2


class TestRetryConfigIntegration:
    """Verify RetryConfig flows through OrcaPlaywrightRunnerConfig correctly."""

    def test_default_harness_config_has_retry(self) -> None:
        config = OrcaPlaywrightRunnerConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )
        assert config.retry.action_max_attempts == 3
        assert config.retry.run_max_retries == 2
        assert config.retry.turn_max_retries == 1
        assert config.retry.consecutive_turn_failures_limit == 2
