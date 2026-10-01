"""OrcaPlaywrightRunnerFactory — manages browser lifecycle and creates runners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.async_api import async_playwright

from metis.core.logging import get_logger

from ._config import OrcaPlaywrightRunnerConfig

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Browser, Playwright

    from ...runner import Runner

logger = get_logger()


class OrcaPlaywrightRunnerFactory:
    """Factory that owns the Playwright browser and creates runners per attempt.

    Note: the runners this factory creates are hardcoded for the Orca chat UI
    (auth flow, selectors, page interactions). For non-Orca browser targets,
    write a new RunnerFactory.

    All configuration comes from OrcaPlaywrightRunnerConfig.load(), which reads
    ORCA_URL, ORCA_USERNAME, ORCA_PASSWORD, and HEADED from environment
    variables. Pass a config explicitly to override (e.g. in tests).
    """

    def __init__(self, config: OrcaPlaywrightRunnerConfig | None = None) -> None:
        self._config = config or OrcaPlaywrightRunnerConfig.load()
        self._headed = self._config.headed
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

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

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> Runner:
        """Create a fresh runner with an isolated browser context."""
        if self._browser is None:
            raise RuntimeError("call start() before create()")
        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        from . import OrcaPlaywrightRunner

        return OrcaPlaywrightRunner(
            page=page,
            config=self._config,
            fixtures_dir=fixtures_dir,
            run_dir=run_dir,
            experiment_root=experiment_root,
        )

    async def close(self) -> None:
        """Shut down browser and Playwright."""
        if self._browser:
            logger.info("[factory] Closing browser...")
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
