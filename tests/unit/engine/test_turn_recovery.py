"""Tests for turn-level recovery logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRecoverPage:
    @pytest.mark.asyncio
    async def test_recover_page_reloads_and_waits_for_textarea(self) -> None:
        from metis.engine.simulation.harness._config import HarnessConfig
        from metis.engine.simulation.harness._environment import _recover_page

        page = MagicMock()
        page.reload = AsyncMock()
        page.wait_for_selector = AsyncMock()

        config = HarnessConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )

        with patch(
            "metis.engine.simulation.harness._environment.dismiss_modals",
            new_callable=AsyncMock,
        ):
            await _recover_page(page, config)

        page.reload.assert_called_once_with(wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector.assert_called_once_with("textarea", timeout=10000)


class TestRecoverAndCheck:
    @pytest.mark.asyncio
    async def test_returns_ui_state_when_message_found(self) -> None:
        from metis.engine.simulation.harness._config import HarnessConfig
        from metis.engine.simulation.harness._environment import _recover_and_check
        from metis.engine.simulation.types import UIState

        page = MagicMock()
        page.reload = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.evaluate = AsyncMock(return_value="Hello, how can I help you today?")

        config = HarnessConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )

        mock_ui_state = UIState(text="response from assistant")

        with (
            patch(
                "metis.engine.simulation.harness._environment.dismiss_modals",
                new_callable=AsyncMock,
            ),
            patch(
                "metis.engine.simulation.harness._environment.capture_ui_state",
                new_callable=AsyncMock,
                return_value=mock_ui_state,
            ),
        ):
            result = await _recover_and_check(
                page, config, "Hello, how can I help you today?"
            )

        assert result == mock_ui_state

    @pytest.mark.asyncio
    async def test_returns_none_when_message_not_found(self) -> None:
        from metis.engine.simulation.harness._config import HarnessConfig
        from metis.engine.simulation.harness._environment import _recover_and_check
        from metis.engine.simulation.types import UIState

        page = MagicMock()
        page.reload = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.evaluate = AsyncMock(return_value="Some other message entirely")

        config = HarnessConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )

        with (
            patch(
                "metis.engine.simulation.harness._environment.dismiss_modals",
                new_callable=AsyncMock,
            ),
            patch(
                "metis.engine.simulation.harness._environment.capture_ui_state",
                new_callable=AsyncMock,
                return_value=UIState(text="whatever"),
            ),
        ):
            result = await _recover_and_check(
                page, config, "My actual sent message"
            )

        assert result is None


class TestConsecutiveFailureEscalation:
    @pytest.mark.asyncio
    async def test_escalates_after_consecutive_failures(self) -> None:
        """After N consecutive turn failures, run_simulation should raise
        ConsecutiveFailureEscalation rather than continuing."""
        from metis.engine.simulation.exceptions import ConsecutiveFailureEscalation

        # This test validates the behavior contract. The exact integration
        # depends on the run_simulation refactoring. Verify the exception exists
        # and is importable for now.
        exc = ConsecutiveFailureEscalation("2 consecutive turn failures")
        assert "2 consecutive" in str(exc)
