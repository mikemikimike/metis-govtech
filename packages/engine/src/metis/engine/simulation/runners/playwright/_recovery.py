"""Lightweight page recovery helpers for the Playwright runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.core.logging import get_logger

from ._auth import dismiss_modals
from ._ui_capture import capture_ui_state

if TYPE_CHECKING:
    from playwright.async_api import Page

    from ...types import UIState
    from ._config import HarnessConfig

logger = get_logger()


async def _recover_page(page: Page, config: HarnessConfig) -> None:
    """Lightweight page recovery: refresh + wait for chat textarea."""
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    await dismiss_modals(page)
    await page.wait_for_selector("textarea", timeout=10000)


async def _recover_and_check(
    page: Page,
    config: HarnessConfig,
    sent_message: str,
) -> UIState | None:
    """Recover page and check whether the sent message got a response.

    Returns UIState if the message was already processed (don't resend),
    or None if the message was never received (safe to resend).
    """
    await _recover_page(page, config)
    ui_state = await capture_ui_state(page)

    last_user_msg = await page.evaluate("""() => {
        const msgs = document.querySelectorAll('[class*="user"], [class*="User"]');
        return msgs.length ? msgs[msgs.length - 1].innerText?.trim() || "" : "";
    }""")

    if sent_message[:80] in (last_user_msg or ""):
        return ui_state
    return None
