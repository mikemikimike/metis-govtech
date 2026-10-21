"""Tests for the intent-based element resolver."""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.exceptions import TransientDOMError
from metis.engine.simulation.gen_1.runners.orca_playwright._element_resolver import (
    AriaStrategy,
    CSSStrategy,
    TextStrategy,
    resolve_element,
)


@pytest.fixture
def mock_page() -> MagicMock:
    page = MagicMock()
    page.locator = MagicMock()
    page.get_by_role = MagicMock()
    page.get_by_text = MagicMock()
    return page


class TestCSSStrategy:
    def test_locate_returns_locator(self, mock_page: MagicMock) -> None:
        strategy = CSSStrategy("button[data-testid='send']")
        locator = strategy.locate(mock_page)
        mock_page.locator.assert_called_once_with("button[data-testid='send']")
        assert locator == mock_page.locator.return_value


class TestAriaStrategy:
    def test_locate_returns_locator(self, mock_page: MagicMock) -> None:
        strategy = AriaStrategy(role="button", name="Send")
        locator = strategy.locate(mock_page)
        mock_page.get_by_role.assert_called_once_with("button", name="Send")
        assert locator == mock_page.get_by_role.return_value


class TestTextStrategy:
    def test_locate_returns_locator(self, mock_page: MagicMock) -> None:
        strategy = TextStrategy("Send")
        locator = strategy.locate(mock_page)
        mock_page.get_by_text.assert_called_once_with("Send")
        assert locator == mock_page.get_by_text.return_value


class TestResolveElement:
    @pytest.mark.asyncio
    async def test_returns_first_visible_enabled_element(
        self, mock_page: MagicMock
    ) -> None:
        locator = MagicMock()
        locator.first = locator
        locator.is_visible = AsyncMock(return_value=True)
        locator.is_enabled = AsyncMock(return_value=True)
        mock_page.locator.return_value = locator

        strategy = CSSStrategy("textarea")
        result = await resolve_element(
            mock_page, intent="chat_textarea", strategies=[strategy]
        )
        assert result == locator

    @pytest.mark.asyncio
    async def test_skips_invisible_element(self, mock_page: MagicMock) -> None:
        invisible_locator = MagicMock()
        invisible_locator.first = invisible_locator
        invisible_locator.is_visible = AsyncMock(return_value=False)

        visible_locator = MagicMock()
        visible_locator.first = visible_locator
        visible_locator.is_visible = AsyncMock(return_value=True)
        visible_locator.is_enabled = AsyncMock(return_value=True)

        mock_page.locator.return_value = invisible_locator
        mock_page.get_by_text.return_value = visible_locator

        strategies = [CSSStrategy("textarea"), TextStrategy("Type a message")]
        result = await resolve_element(
            mock_page, intent="chat_textarea", strategies=strategies
        )
        assert result == visible_locator

    @pytest.mark.asyncio
    async def test_raises_transient_dom_error_when_all_fail(
        self, mock_page: MagicMock
    ) -> None:
        locator = MagicMock()
        locator.first = locator
        locator.is_visible = AsyncMock(return_value=False)
        mock_page.locator.return_value = locator

        with pytest.raises(TransientDOMError, match="chat_textarea"):
            await resolve_element(
                mock_page, intent="chat_textarea", strategies=[CSSStrategy("textarea")]
            )

    @pytest.mark.asyncio
    async def test_handles_timeout_from_locator(self, mock_page: MagicMock) -> None:
        from playwright.async_api import Error as PlaywrightError

        locator = MagicMock()
        locator.first = locator
        locator.is_visible = AsyncMock(side_effect=PlaywrightError("Timeout"))

        visible_locator = MagicMock()
        visible_locator.first = visible_locator
        visible_locator.is_visible = AsyncMock(return_value=True)
        visible_locator.is_enabled = AsyncMock(return_value=True)
        mock_page.get_by_role.return_value = visible_locator
        mock_page.locator.return_value = locator

        strategies = [CSSStrategy("div"), AriaStrategy(role="textbox", name="Message")]
        result = await resolve_element(mock_page, intent="input", strategies=strategies)
        assert result == visible_locator
