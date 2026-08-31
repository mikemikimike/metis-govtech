"""Tests for the simulation exception hierarchy."""

from metis.engine.simulation.exceptions import (
    AuthLossError,
    ConsecutiveFailureEscalation,
    PageCrashError,
    PostSubmissionObservationError,
    ResponseTimeoutError,
    RunRecoverableError,
    SimulationError,
    TargetSessionEnded,
    TargetSessionLostError,
    TargetUnavailableError,
    TransientDOMError,
    TurnRecoverableError,
)


class TestExceptionHierarchy:
    def test_turn_recoverable_is_simulation_error(self) -> None:
        assert issubclass(TurnRecoverableError, SimulationError)

    def test_run_recoverable_is_simulation_error(self) -> None:
        assert issubclass(RunRecoverableError, SimulationError)

    def test_transient_dom_is_turn_recoverable(self) -> None:
        assert issubclass(TransientDOMError, TurnRecoverableError)

    def test_post_submission_is_turn_recoverable(self) -> None:
        assert issubclass(PostSubmissionObservationError, TurnRecoverableError)

    def test_auth_loss_is_run_recoverable(self) -> None:
        assert issubclass(AuthLossError, RunRecoverableError)

    def test_page_crash_is_run_recoverable(self) -> None:
        assert issubclass(PageCrashError, RunRecoverableError)

    def test_consecutive_failure_is_run_recoverable(self) -> None:
        assert issubclass(ConsecutiveFailureEscalation, RunRecoverableError)

    def test_response_timeout_is_simulation_error(self) -> None:
        assert issubclass(ResponseTimeoutError, SimulationError)

    def test_response_timeout_is_not_turn_or_run_recoverable(self) -> None:
        assert not issubclass(ResponseTimeoutError, TurnRecoverableError)
        assert not issubclass(ResponseTimeoutError, RunRecoverableError)

    def test_exception_messages(self) -> None:
        exc = TransientDOMError("textarea not found after 3 strategies")
        assert "textarea not found" in str(exc)

        exc = AuthLossError("redirected to /login")
        assert "/login" in str(exc)


def test_target_unavailable_is_turn_recoverable() -> None:
    assert issubclass(TargetUnavailableError, TurnRecoverableError)


def test_target_session_lost_is_run_recoverable() -> None:
    assert issubclass(TargetSessionLostError, RunRecoverableError)


def test_target_session_ended_is_simulation_error() -> None:
    assert issubclass(TargetSessionEnded, SimulationError)
    assert not issubclass(TargetSessionEnded, TurnRecoverableError)
    assert not issubclass(TargetSessionEnded, RunRecoverableError)
