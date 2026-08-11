"""Authentication and modal dismissal for the target web UI."""

from playwright.async_api import Page

from metis.core.logging import get_logger

from ._config import HarnessConfig
from ._protocol import expect, stabilize

logger = get_logger()


async def dismiss_modals(page: Page) -> None:
    """Aggressively dismiss any modal/dialog overlay blocking interactions."""
    logger.debug("[modal] Attempting to dismiss modals...")

    # Strategy 1: Click "Skip for now" (onboarding tour)
    try:
        skip_btn = page.get_by_text("Skip for now")
        if await skip_btn.is_visible(timeout=1000):
            logger.info("[modal] Clicking 'Skip for now' (onboarding tour)")
            skip_btn.click()
            stabilize(page, "modal dismiss after 'Skip for now'", 500)
    except Exception:
        pass

    # Strategy 2: Click close/dismiss buttons with common labels
    try:
        for text in ("Close", "Got it", "Dismiss"):
            btn = page.get_by_text(text, exact=True)
            if await btn.is_visible(timeout=500):
                logger.info("[modal] Clicking '%s' button", text)
                btn.click()
                stabilize(page, f"modal dismiss after '{text}'", 500)
                break
    except Exception:
        pass

    # Strategy 3: Click a safe dismiss button inside a dialog element
    try:
        dialog = page.locator('[role="dialog"]')
        if dialog.first.is_visible(timeout=500):
            safe_btn = dialog.locator(
                'button:has-text("Cancel"), '
                'button:has-text("Close"), '
                'button:has-text("Dismiss"), '
                'button:has-text("Got it"), '
                'button:has-text("OK")'
            ).first
            if safe_btn.is_visible(timeout=500):
                logger.info("[modal] Clicking safe dialog button")
                safe_btn.click()
                stabilize(page, "modal dismiss after dialog button click", 500)
    except Exception:
        pass

    # Strategy 4: Click aria-label="Close" button
    try:
        aria_close = page.locator('[aria-label="Close"]')
        if await aria_close.first.is_visible(timeout=500):
            logger.info("[modal] Clicking aria-label='Close' button")
            aria_close.first.click()
            stabilize(page, "modal dismiss after aria-close click", 500)
    except Exception:
        pass

    # Strategy 5: Press Escape only if a dialog is still present
    try:
        if page.locator('[role="dialog"]').first.is_visible(timeout=500):
            logger.info("[modal] Dialog still present — pressing Escape")
            page.keyboard.press("Escape")
            stabilize(page, "modal dismiss after Escape key", 500)
    except Exception:
        pass

    # Strategy 6: Click outside the dialog (backdrop) to dismiss
    try:
        dialog = page.locator('[role="dialog"]')
        if dialog.first.is_visible(timeout=500):
            # Click at top-left corner of viewport — outside the centered dialog
            logger.info("[modal] Clicking outside dialog (backdrop)")
            page.mouse.click(5, 5)
            stabilize(page, "modal dismiss after backdrop click", 500)
    except Exception:
        pass

    # Nuclear: if dialog still visible, remove from DOM
    try:
        dialog_still_visible = await page.locator('[role="dialog"]').first.is_visible(
            timeout=500
        )
        if dialog_still_visible:
            logger.info("[modal] Nuclear: removing dialog elements from DOM")
            await page.evaluate(
                """() => {
                document.querySelectorAll('[role="dialog"]').forEach(d => d.remove());
                // Remove any overlay siblings (common pattern: fixed overlay before dialog)
                document.querySelectorAll('[aria-hidden="true"]').forEach(o => {
                    if (o.style.position === 'fixed' || getComputedStyle(o).position === 'fixed') {
                        o.remove();
                    }
                });
            }"""
            )
            stabilize(page, "DOM mutation after dialog removal", 300)
    except Exception:
        pass


async def login(page: Page, config: HarnessConfig) -> None:
    """Log in to Orca via WOG AD and navigate to a fresh chat."""
    logger.info("[login] Step 1/8: Navigating to %s ...", config.url)
    await page.goto(config.url, wait_until="networkidle", timeout=60000)
    logger.info("[login] Step 1/8: Page loaded (URL: %s)", page.url)

    # Click "Log in with WOG AD" — navigates to /auth/signin.
    logger.info(
        "[login] Step 2/8: Clicking '%s' link...", config.auth.login_button_text
    )
    await (
        page.get_by_role("banner")
        .get_by_role("link", name=config.auth.login_button_text)
        .click(timeout=15000)
    )
    await page.wait_for_load_state("networkidle", timeout=60000)
    logger.info("[login] Step 2/8: On signin page (URL: %s)", page.url)

    # Click "Log in with user ID" on the /auth/signin intermediate page.
    logger.info("[login] Step 3/8: Clicking '%s'...", config.auth.userid_button_text)
    await page.get_by_role("button", name=config.auth.userid_button_text).click(
        timeout=15000
    )

    # Wait for the redirect chain to the external identity provider.
    logger.info("[login] Step 4/8: Waiting for OAuth redirect (networkidle)...")
    await page.wait_for_load_state("networkidle", timeout=60000)
    logger.info("[login] Step 4/8: Redirect complete (URL: %s)", page.url)

    # Now wait for the IdP login form (username field) to appear.
    logger.info("[login] Step 5/8: Waiting for IdP login form...")
    username_locator = page.get_by_label("username", exact=False)
    await username_locator.wait_for(state="visible", timeout=60000)
    logger.info("[login] Step 5/8: IdP form visible — filling credentials")
    await username_locator.fill(config.auth.username)
    await page.get_by_label("password", exact=False).fill(config.auth.password)

    # Click "Sign in"
    logger.info("[login] Step 6/8: Clicking '%s'...", config.auth.signin_button_text)
    await page.get_by_role("button", name=config.auth.signin_button_text).click()

    # Wait for app to load post-login
    logger.info("[login] Step 7/8: Waiting for app to load after sign-in...")
    expect(
        page,
        description="app loaded post-login",
        predicate="""() => {
            return !!document.querySelector('textarea') ||
                   document.body.innerText.includes('New chat');
        }""",
        timeout_ms=15000,
    )
    logger.info("[login] Step 7/8: Post-login URL: %s", page.url)
    try:
        await page.get_by_text("New chat").click(timeout=5000)
        logger.info("[login] Step 7/8: Clicked 'New chat'")
    except Exception:
        logger.info("[login] Step 7/8: 'New chat' not found — navigating to /chat")
        page.goto(config.url + "/chat", wait_until="domcontentloaded", timeout=15000)

    # Wait for chat to be ready
    expect(
        page,
        description="chat textarea ready",
        predicate="() => !!document.querySelector('textarea')",
        timeout_ms=10000,
    )

    # Dismiss modals
    logger.info("[login] Step 8/8: Dismissing modals...")
    await dismiss_modals(page)

    # Final readiness check
    page.wait_for_selector("textarea", timeout=10000)
    logger.info("[login] Login complete — chat textarea ready (URL: %s)", page.url)
