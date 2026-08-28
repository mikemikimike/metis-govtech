"""Tests for PlaywrightRunnerFactory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestPlaywrightRunnerFactoryInit:
    def test_from_env_loads_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORCA_URL", "https://example.com")
        monkeypatch.setenv("ORCA_USERNAME", "user")
        monkeypatch.setenv("ORCA_PASSWORD", "pass")

        from metis.engine.simulation.runners.playwright._factory import (
            PlaywrightRunnerFactory,
        )

        factory = PlaywrightRunnerFactory.from_env(headed=False)
        assert factory._config.url == "https://example.com"
        assert factory._config.auth.username == "user"
        assert factory._headed is False

    def test_retry_defaults_from_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORCA_URL", "https://example.com")
        monkeypatch.setenv("ORCA_USERNAME", "user")
        monkeypatch.setenv("ORCA_PASSWORD", "pass")

        from metis.engine.simulation.runners.playwright._factory import (
            PlaywrightRunnerFactory,
        )

        factory = PlaywrightRunnerFactory.from_env(headed=False)
        max_retries, delay = factory.retry_defaults
        assert max_retries == 2
        assert delay == 5.0


class TestPlaywrightRunnerFactoryLifecycle:
    @pytest.mark.asyncio
    async def test_start_launches_browser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCA_URL", "https://example.com")
        monkeypatch.setenv("ORCA_USERNAME", "user")
        monkeypatch.setenv("ORCA_PASSWORD", "pass")

        from metis.engine.simulation.runners.playwright._factory import (
            PlaywrightRunnerFactory,
        )

        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_fn = AsyncMock()
        mock_playwright_fn.start = AsyncMock(return_value=mock_pw)

        with patch(
            "metis.engine.simulation.runners.playwright._factory.async_playwright",
            return_value=mock_playwright_fn,
        ):
            factory = PlaywrightRunnerFactory.from_env(headed=True)
            await factory.start()

            mock_pw.chromium.launch.assert_called_once_with(headless=False)

    @pytest.mark.asyncio
    async def test_create_returns_playwright_runner(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("ORCA_URL", "https://example.com")
        monkeypatch.setenv("ORCA_USERNAME", "user")
        monkeypatch.setenv("ORCA_PASSWORD", "pass")

        from metis.engine.simulation.runners.playwright import PlaywrightRunner
        from metis.engine.simulation.runners.playwright._factory import (
            PlaywrightRunnerFactory,
        )

        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        factory = PlaywrightRunnerFactory.from_env(headed=False)
        factory._browser = mock_browser

        runner = await factory.create(tmp_path / "run", tmp_path / "fixtures")
        assert isinstance(runner, PlaywrightRunner)
        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )

    @pytest.mark.asyncio
    async def test_close_shuts_down_browser_and_playwright(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCA_URL", "https://example.com")
        monkeypatch.setenv("ORCA_USERNAME", "user")
        monkeypatch.setenv("ORCA_PASSWORD", "pass")

        from metis.engine.simulation.runners.playwright._factory import (
            PlaywrightRunnerFactory,
        )

        factory = PlaywrightRunnerFactory.from_env(headed=False)
        factory._browser = AsyncMock()
        factory._pw = AsyncMock()

        await factory.close()
        factory._browser.close.assert_called_once()
        factory._pw.stop.assert_called_once()
