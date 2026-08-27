"""PlaywrightRunnerFactory — manages browser lifecycle and creates runners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.async_api import async_playwright

from metis.core.logging import get_logger

from ._config import PlaywrightRunnerConfig

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Browser, Playwright

    from ...runner import Runner

logger = get_logger()


class PlaywrightRunnerFactory:
    """Factory that owns the Playwright browser and creates runners per attempt.

    Note: configuration (ORCA_URL, ORCA_USERNAME, ORCA_PASSWORD env vars) and
    the runners it creates are hardcoded for the Orca chat UI.
    """

    def __init__(self, config: PlaywrightRunnerConfig, headed: bool = False) -> None:
        self._config = config
        self._headed = headed
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    @classmethod
    def from_env(cls, headed: bool = False) -> PlaywrightRunnerFactory:
        """Construct from environment variables (loads PlaywrightRunnerConfig)."""
        config = PlaywrightRunnerConfig.load()
        return cls(config=config, headed=headed)

    @property
    def retry_defaults(self) -> tuple[int, float]:
        """Return (run_max_retries, run_retry_delay_seconds) from config."""
        return (
            self._config.retry.run_max_retries,
            self._config.retry.run_retry_delay_seconds,
        )

    async def start(self) -> None:
        """Launch Playwright and the browser."""
        self._pw = await async_playwright().start()
        logger.info(
            "[factory] Launching Chromium (%s mode)...",
            "headed" if self._headed else "headless",
        )
        self._browser = await self._pw.chromium.launch(headless=not self._headed)

    async def create(self, run_dir: Path, fixtures_dir: Path) -> Runner:
        """Create a fresh runner with an isolated browser context."""
        if self._browser is None:
            raise RuntimeError("call start() before create()")
        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        from . import PlaywrightRunner

        return PlaywrightRunner(
            page=page,
            config=self._config,
            fixtures_dir=fixtures_dir,
            run_dir=run_dir,
        )

    async def close(self) -> None:
        """Shut down browser and Playwright."""
        if self._browser:
            logger.info("[factory] Closing browser...")
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
