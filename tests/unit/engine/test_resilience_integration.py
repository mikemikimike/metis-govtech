"""Integration tests for the full resilience stack."""

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.exceptions import (
    AuthLossError,
    ConsecutiveFailureEscalation,
    PageCrashError,
    PostSubmissionObservationError,
    ResponseTimeoutError,
    SimulationError,
    TransientDOMError,
    TrialRecoverableError,
    TurnRecoverableError,
)
from metis.engine.simulation.gen_1.runners.orca_playwright._config import (
    OrcaPlaywrightRunnerConfig,
)
from metis.engine.simulation.gen_1.runners.orca_playwright._element_resolver import (
    resolve_element,
)
from metis.engine.simulation.gen_1.runners.orca_playwright._retry import (
    action_retry,
    track_submission,
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
            importlib.import_module("metis.engine.simulation.gen_1.orchestrator")
        )
        importlib.reload(
            importlib.import_module(
                "metis.engine.simulation.gen_1.runners.orca_playwright"
            )
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

    def test_trial_layer_catches_auth_loss(self) -> None:
        try:
            raise AuthLossError("redirected")
        except TrialRecoverableError:
            pass  # correct

    def test_trial_layer_catches_page_crash(self) -> None:
        try:
            raise PageCrashError("disconnected")
        except TrialRecoverableError:
            pass  # correct

    def test_trial_layer_catches_escalation(self) -> None:
        try:
            raise ConsecutiveFailureEscalation("3 failures")
        except TrialRecoverableError:
            pass  # correct

    def test_response_timeout_not_caught_by_turn_or_trial(self) -> None:
        with pytest.raises(ResponseTimeoutError):
            try:
                raise ResponseTimeoutError("polling expired")
            except (TurnRecoverableError, TrialRecoverableError):
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


class TestRetryConfigIntegration:
    """Verify RetryConfig flows through OrcaPlaywrightRunnerConfig correctly."""

    def test_default_harness_config_has_retry(self) -> None:
        config = OrcaPlaywrightRunnerConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )
        assert config.retry.action_max_attempts == 3
        assert config.retry.trial_max_retries == 2
        assert config.retry.turn_max_retries == 1
        assert config.retry.consecutive_turn_failures_limit == 2
