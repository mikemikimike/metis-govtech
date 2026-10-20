"""Lightweight page recovery helpers for the Playwright runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.core.logging import get_logger

from ._auth import dismiss_modals

if TYPE_CHECKING:
    from playwright.async_api import Page

    from ._config import OrcaPlaywrightRunnerConfig

logger = get_logger()


async def _recover_page(page: Page, config: OrcaPlaywrightRunnerConfig) -> None:
    """Lightweight page recovery: refresh + wait for chat textarea."""
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    await dismiss_modals(page)
    await page.wait_for_selector("textarea", timeout=10000)
