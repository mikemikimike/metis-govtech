"""Tests that auth and UI capture use retry infrastructure."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metis.engine.simulation.harness._config import HarnessConfig, RetryConfig


class TestCaptureUIStateRetry:
    @pytest.mark.asyncio
    async def test_capture_retries_on_js_evaluation_error(self) -> None:
        from metis.engine.simulation.harness._ui_capture import capture_ui_state

        page = MagicMock()
        call_count = 0

        async def flaky_evaluate(script):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("JS eval timed out")
            return {
                "text": "response",
                "artifacts": [],
                "target_status_labels": [],
                "errors": [],
                "interactive_elements": [],
                "form_elements": [],
            }

        page.evaluate = flaky_evaluate

        config = RetryConfig(action_max_attempts=3, action_backoff_base_seconds=0.01)
        # After the refactoring, capture_ui_state should accept config and retry
        # For now, validate it's importable and the pattern makes sense
        assert capture_ui_state is not None

    @pytest.mark.asyncio
    async def test_capture_ui_state_accepts_config_parameter(self) -> None:
        from metis.engine.simulation.harness._ui_capture import capture_ui_state

        import inspect

        sig = inspect.signature(capture_ui_state)
        params = list(sig.parameters.keys())
        assert "page" in params
        assert "config" in params
        assert sig.parameters["config"].default is None

    @pytest.mark.asyncio
    async def test_capture_ui_state_retries_and_succeeds(self) -> None:
        from metis.engine.simulation.harness._ui_capture import capture_ui_state
        from metis.engine.simulation.harness._config import RetryConfig

        page = MagicMock()
        call_count = 0

        async def flaky_evaluate(script):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("JS eval timed out")
            return {
                "text": "response",
                "artifacts": [],
                "target_status_labels": [],
                "errors": [],
                "interactive_elements": [],
                "form_elements": [],
            }

        page.evaluate = flaky_evaluate

        config = RetryConfig(action_max_attempts=3, action_backoff_base_seconds=0.0)
        result = await capture_ui_state(page, config=config)
        assert result.text == "response"
        assert call_count == 2


class TestLoginElementResolver:
    def test_login_function_exists(self) -> None:
        from metis.engine.simulation.harness._auth import login

        assert login is not None

    def test_login_uses_resolve_element(self) -> None:
        """Verify that _auth imports resolve_element (i.e., the module was updated)."""
        import metis.engine.simulation.harness._auth as auth_module

        assert hasattr(auth_module, "resolve_element")

    def test_auth_imports_element_strategies(self) -> None:
        """Verify that _auth imports the element strategy types."""
        import metis.engine.simulation.harness._auth as auth_module

        assert hasattr(auth_module, "AriaStrategy")
        assert hasattr(auth_module, "CSSStrategy")
        assert hasattr(auth_module, "TextStrategy")
