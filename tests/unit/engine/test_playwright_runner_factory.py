"""Tests for OrcaPlaywrightRunnerFactory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.runners.orca_playwright._config import (
    AuthConfig,
    OrcaPlaywrightRunnerConfig,
)


def _make_config(*, headed: bool = False) -> OrcaPlaywrightRunnerConfig:
    return OrcaPlaywrightRunnerConfig(
        url="https://example.com",
        auth=AuthConfig(username="user", password="pass"),
        headed=headed,
    )


class TestPlaywrightRunnerFactoryInit:
    def test_init_with_explicit_config(self) -> None:
        from metis.engine.simulation.runners.orca_playwright._factory import (
            OrcaPlaywrightRunnerFactory,
        )

        config = _make_config(headed=False)
        factory = OrcaPlaywrightRunnerFactory(config=config)
        assert factory._config.url == "https://example.com"
        assert factory._config.auth.username == "user"
        assert factory._headed is False

    def test_init_loads_from_env_when_no_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCA_URL", "https://env.example.com")
        monkeypatch.setenv("ORCA_USERNAME", "env_user")
        monkeypatch.setenv("ORCA_PASSWORD", "env_pass")
        monkeypatch.setenv("HEADED", "true")

        from metis.engine.simulation.runners.orca_playwright._factory import (
            OrcaPlaywrightRunnerFactory,
        )

        factory = OrcaPlaywrightRunnerFactory()
        assert factory._config.url == "https://env.example.com"
        assert factory._config.auth.username == "env_user"
        assert factory._headed is True

    def test_retry_defaults_from_config(self) -> None:
        from metis.engine.simulation.runners.orca_playwright._factory import (
            OrcaPlaywrightRunnerFactory,
        )

        factory = OrcaPlaywrightRunnerFactory(config=_make_config())
        max_retries, delay = factory.retry_defaults
        assert max_retries == 2
        assert delay == 5.0


class TestPlaywrightRunnerFactoryLifecycle:
    @pytest.mark.asyncio
    async def test_start_launches_browser_headed(self) -> None:
        from metis.engine.simulation.runners.orca_playwright._factory import (
            OrcaPlaywrightRunnerFactory,
        )

        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_fn = AsyncMock()
        mock_playwright_fn.start = AsyncMock(return_value=mock_pw)

        with patch(
            "metis.engine.simulation.runners.orca_playwright._factory.async_playwright",
            return_value=mock_playwright_fn,
        ):
            factory = OrcaPlaywrightRunnerFactory(config=_make_config(headed=True))
            await factory.start()

            mock_pw.chromium.launch.assert_called_once_with(headless=False)

    @pytest.mark.asyncio
    async def test_create_returns_playwright_runner(self, tmp_path: Path) -> None:
        from metis.engine.simulation.runners.orca_playwright import OrcaPlaywrightRunner
        from metis.engine.simulation.runners.orca_playwright._factory import (
            OrcaPlaywrightRunnerFactory,
        )

        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        factory = OrcaPlaywrightRunnerFactory(config=_make_config())
        factory._browser = mock_browser

        runner = await factory.create(tmp_path / "run", tmp_path / "fixtures", tmp_path)
        assert isinstance(runner, OrcaPlaywrightRunner)
        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )

    @pytest.mark.asyncio
    async def test_close_shuts_down_browser_and_playwright(self) -> None:
        from metis.engine.simulation.runners.orca_playwright._factory import (
            OrcaPlaywrightRunnerFactory,
        )

        factory = OrcaPlaywrightRunnerFactory(config=_make_config())
        factory._browser = AsyncMock()
        factory._pw = AsyncMock()

        await factory.close()
        factory._browser.close.assert_called_once()
        factory._pw.stop.assert_called_once()


@pytest.mark.asyncio
async def test_run_response_wait_is_applied_without_changing_shared_config(
    tmp_path: Path,
) -> None:
    from metis.engine.simulation.runners.orca_playwright import OrcaPlaywrightRunner
    from metis.engine.simulation.types import RunConfig

    shared = _make_config()
    runner = OrcaPlaywrightRunner(
        page=AsyncMock(),
        config=shared,
        fixtures_dir=tmp_path,
        run_dir=tmp_path,
        experiment_root=tmp_path,
    )
    with patch(
        "metis.engine.simulation.runners.orca_playwright.login", new_callable=AsyncMock
    ) as login:
        await runner.setup(RunConfig(persona="p", scenario="s", response_wait_ms=45000))
    assert runner._config.timeouts.response_wait_ms == 45000
    assert shared.timeouts.response_wait_ms == 300000
    assert login.await_args is not None
    assert login.await_args.args[1].timeouts.response_wait_ms == 45000
