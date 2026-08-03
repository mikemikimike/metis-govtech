"""Authentication and modal dismissal for the target web UI."""

from playwright.sync_api import Page

from metis.core.logging import get_logger

from ._config import HarnessConfig

logger = get_logger()


def dismiss_modals(page: Page) -> None:
    """Aggressively dismiss any modal/dialog overlay blocking interactions."""
    logger.debug("[modal] Attempting to dismiss modals...")

    # Strategy 1: Click "Skip for now" (onboarding tour)
    try:
        skip_btn = page.get_by_text("Skip for now")
        if skip_btn.is_visible(timeout=1000):
            logger.info("[modal] Clicking 'Skip for now' (onboarding tour)")
            skip_btn.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # Strategy 2: Click close/dismiss buttons with common labels
    try:
        for text in ("Close", "Got it", "Dismiss"):
            btn = page.get_by_text(text, exact=True)
            if btn.is_visible(timeout=500):
                logger.info("[modal] Clicking '%s' button", text)
                btn.click()
                page.wait_for_timeout(500)
                break
    except Exception:
        pass

    # Strategy 3: Click any button inside a dialog element
    try:
        dialog_btn = page.locator('[role="dialog"] button')
        if dialog_btn.first.is_visible(timeout=500):
            logger.info("[modal] Clicking first button inside dialog")
            dialog_btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # Strategy 4: Click aria-label="Close" button
    try:
        aria_close = page.locator('[aria-label="Close"]')
        if aria_close.first.is_visible(timeout=500):
            logger.info("[modal] Clicking aria-label='Close' button")
            aria_close.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # Strategy 5: Press Escape to dismiss modal
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass

    # Strategy 6: Click the backdrop overlay to dismiss
    try:
        backdrop = page.locator('[role="dialog"] .absolute.inset-0')
        if backdrop.first.is_visible(timeout=500):
            logger.info("[modal] Clicking backdrop overlay")
            backdrop.first.click(position={"x": 10, "y": 10}, force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass

    # Nuclear: if dialog still visible, remove from DOM
    try:
        dialog_still_visible = page.locator('[role="dialog"]').first.is_visible(
            timeout=500
        )
        if dialog_still_visible:
            logger.info("[modal] Nuclear: removing dialog elements from DOM")
            page.evaluate(
                """() => {
                document.querySelectorAll('[role="dialog"]').forEach(d => d.remove());
                document.querySelectorAll('.fixed.inset-0[class*="bg-"]').forEach(o => o.remove());
            }"""
            )
            page.wait_for_timeout(300)
    except Exception:
        pass


def login(page: Page, config: HarnessConfig) -> None:
    """Log in to Orca via WOG AD and navigate to a fresh chat."""
    logger.info("[login] Step 1/8: Navigating to %s ...", config.url)
    page.goto(config.url, wait_until="networkidle", timeout=60000)
    logger.info("[login] Step 1/8: Page loaded (URL: %s)", page.url)

    # Click "Log in with WOG AD" — navigates to /auth/signin.
    logger.info(
        "[login] Step 2/8: Clicking '%s' link...", config.auth.login_button_text
    )
    page.get_by_role("banner").get_by_role(
        "link", name=config.auth.login_button_text
    ).click(timeout=15000)
    page.wait_for_load_state("networkidle", timeout=60000)
    logger.info("[login] Step 2/8: On signin page (URL: %s)", page.url)

    # Click "Log in with user ID" on the /auth/signin intermediate page.
    logger.info("[login] Step 3/8: Clicking '%s'...", config.auth.userid_button_text)
    page.get_by_role("button", name=config.auth.userid_button_text).click(timeout=15000)

    # Wait for the redirect chain to the external identity provider.
    logger.info("[login] Step 4/8: Waiting for OAuth redirect (networkidle)...")
    page.wait_for_load_state("networkidle", timeout=60000)
    logger.info("[login] Step 4/8: Redirect complete (URL: %s)", page.url)

    # Now wait for the IdP login form (username field) to appear.
    logger.info("[login] Step 5/8: Waiting for IdP login form...")
    username_locator = page.get_by_label("username", exact=False)
    username_locator.wait_for(state="visible", timeout=60000)
    logger.info("[login] Step 5/8: IdP form visible — filling credentials")
    username_locator.fill(config.auth.username)
    page.get_by_label("password", exact=False).fill(config.auth.password)

    # Click "Sign in"
    logger.info("[login] Step 6/8: Clicking '%s'...", config.auth.signin_button_text)
    page.get_by_role("button", name=config.auth.signin_button_text).click()

    # Wait for app to load, then navigate to fresh chat
    logger.info("[login] Step 7/8: Waiting for app to load after sign-in...")
    page.wait_for_timeout(3000)
    logger.info("[login] Step 7/8: Post-login URL: %s", page.url)
    try:
        page.get_by_text("New chat").click(timeout=5000)
        logger.info("[login] Step 7/8: Clicked 'New chat'")
    except Exception:
        logger.info("[login] Step 7/8: 'New chat' not found — navigating to /chat")
        page.goto(config.url + "/chat", wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(2000)

    # Dismiss modals
    logger.info("[login] Step 8/8: Dismissing modals...")
    dismiss_modals(page)

    # Wait for chat textarea to be ready
    page.wait_for_selector("textarea", timeout=10000)
    logger.info("[login] Login complete — chat textarea ready (URL: %s)", page.url)
