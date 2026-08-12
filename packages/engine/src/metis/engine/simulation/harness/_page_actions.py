"""Browser interactions — send messages, upload files, fill forms."""

import re
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from metis.core.logging import get_logger

from ..exceptions import ResponseTimeoutError
from ..types import UIState
from ._auth import dismiss_modals
from ._config import HarnessConfig
from ._element_resolver import AriaStrategy, CSSStrategy, resolve_element
from ._retry import action_retry, track_submission
from ._ui_capture import capture_ui_state

logger = get_logger()


async def send_message(
    page: Page,
    message: str,
    config: HarnessConfig,
    timeout_override: int | None = None,
) -> UIState:
    """Send a message in the chat and wait for the full response."""
    timeout = timeout_override or config.timeouts.response_wait_ms

    @action_retry(config.retry)
    async def _send() -> UIState:
        msg_preview = message[:80] + ("..." if len(message) > 80 else "")
        logger.info("[send_message] Sending: %r (timeout=%dms)", msg_preview, timeout)

        # Snapshot pre-state (placeholder + message count)
        logger.debug("[send_message] Capturing pre-state snapshot...")
        pre_state = await page.evaluate("""() => {
            const textarea = document.querySelector("textarea");
            const placeholder = textarea?.getAttribute("placeholder") || "";
            const messages = document.querySelectorAll(
              '.message-user, .message-assistant');
            return { placeholder, messageCount: messages.length };
        }""")
        logger.debug(
            "[send_message] Pre-state: placeholder=%r, messageCount=%d",
            pre_state["placeholder"],
            pre_state["messageCount"],
        )

        # Find the CHAT textarea — not form textareas that may appear above it.
        # Primary strategy: match by Orca's known placeholder patterns.
        input_el = await resolve_element(
            page,
            intent="chat_textarea",
            strategies=[
                CSSStrategy(
                    'textarea[placeholder*="Ask anything"], '
                    'textarea[placeholder*="Reply"]'
                ),
                AriaStrategy(role="textbox", name="Message"),
                CSSStrategy("textarea"),
            ],
        )

        logger.info("[send_message] Typing message and pressing Enter...")
        await input_el.fill(message)
        await page.wait_for_timeout(200)
        await input_el.press("Enter")
        track_submission()

        # Wait for response using dual-condition approach
        logger.info("[send_message] Waiting for response (initial 3s buffer)...")
        await page.wait_for_timeout(3000)
        placeholder_already_reply = "Reply" in pre_state["placeholder"]

        logger.info(
            "[send_message] Waiting for new message or placeholder change (timeout=%dms)...",
            timeout,
        )
        try:
            await page.wait_for_function(
                """({ prevCount, alreadyReply }) => {
                    const textarea = document.querySelector("textarea");
                    if (!textarea) return false;
                    const currentPlaceholder =
                      textarea.getAttribute("placeholder") || "";
                    const messages = document.querySelectorAll(
                      '.message-user, .message-assistant');
                    const currentCount = messages.length;
                    const placeholderChanged =
                      !alreadyReply && currentPlaceholder.includes("Reply");
                    const newMessageAppeared = currentCount > prevCount;
                    return placeholderChanged || newMessageAppeared;
                }""",
                arg={
                    "prevCount": pre_state["messageCount"],
                    "alreadyReply": placeholder_already_reply,
                },
                timeout=timeout,
            )
        except PlaywrightTimeoutError:
            raise ResponseTimeoutError(
                f"Response polling timed out after {timeout}ms"
            ) from None
        logger.info(
            "[send_message] Response detected — polling for processing completion..."
        )

        # Poll for processing completion
        poll_deadline = time.time() * 1000 + 300000
        poll_count = 0
        while time.time() * 1000 < poll_deadline:
            still_processing = await page.evaluate("""() => {
                const buttons =
                  Array.from(document.querySelectorAll('button'));
                const hasStop = buttons.some(
                  b => b.textContent?.includes('Stop generating'));
                const lastAssistant = document.querySelector(
                  '.message-assistant:last-of-type');
                const isStreaming = lastAssistant
                  && lastAssistant.innerText.trim() === '';
                return hasStop || isStreaming;
            }""")
            if not still_processing:
                break
            poll_count += 1
            if poll_count % 5 == 1:
                logger.info("[send_message] Still processing (poll #%d)...", poll_count)
            await page.wait_for_timeout(2000)

        if poll_count > 0:
            logger.info(
                "[send_message] Processing complete after %d poll(s)", poll_count
            )

        # Final buffer for remaining streaming
        logger.debug("[send_message] Final 2s buffer...")
        await page.wait_for_timeout(2000)

        logger.info("[send_message] Capturing UI state...")
        ui_state = await capture_ui_state(page)

        # Detect "Response cancelled" — Orca shows this when we interrupted
        # its generation. Wait for the real response that follows.
        if ui_state.text.strip().lower() in (
            "response cancelled",
            "response cancelled.",
        ):
            logger.info(
                "[send_message] Detected 'Response cancelled' — waiting for real response..."
            )
            try:
                await page.wait_for_function(
                    """({ prevCount }) => {
                        return document.querySelectorAll(
                          '.message-user, .message-assistant'
                        ).length > prevCount;
                    }""",
                    arg={"prevCount": pre_state["messageCount"] + 1},
                    timeout=120000,
                )
                await page.wait_for_timeout(2000)
                ui_state = await capture_ui_state(page)
            except Exception:
                pass

        return ui_state

    return await _send()


async def upload_file(
    page: Page, file_path: Path, config: HarnessConfig | None = None
) -> None:
    """Upload a file via the target system's attach-file flow."""
    filename = file_path.name
    logger.info("[upload] Step 1/5: Starting upload of '%s' (%s)", filename, file_path)

    await dismiss_modals(page)

    # Click the attach button to trigger file chooser
    logger.info("[upload] Step 2/5: Clicking attach button...")
    attach_selector = ", ".join(
        [
            'button:has(span.sr-only:has-text("Attach file"))',
            'button:has(span:has-text("Attach file"))',
            'button:has-text("Attach file")',
            'button[aria-label*="attach" i]',
            'button[aria-label*="file" i]',
        ]
    )
    attach_button = page.locator(attach_selector).first

    # Use expect_file_chooser context manager
    file_chooser = None
    try:
        async with page.expect_file_chooser(timeout=10000) as fc_info:
            await attach_button.click(timeout=5000)
        file_chooser = await fc_info.value
        logger.info("[upload] Step 3/5: File chooser opened — setting file...")
    except Exception:
        logger.info(
            "[upload] Step 3/5: File chooser failed — using fallback input[type=file]"
        )

    if file_chooser:
        await file_chooser.set_files(str(file_path))
    else:
        # Fallback: find input[type="file"] and set directly
        file_input = page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(str(file_path))

    await page.wait_for_timeout(2000)

    # Check for "Unsupported format" error — retry with .txt extension (once)
    has_unsupported = await page.evaluate(
        "() => document.body.innerText.includes('Unsupported format')"
    )
    if has_unsupported and file_path.suffix != ".txt":
        logger.info(
            "[upload] Unsupported format detected — retrying '%s' as .txt", filename
        )
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1000)
        with TemporaryDirectory() as tmp_dir:
            txt_path = Path(tmp_dir) / file_path.with_suffix(".txt").name
            shutil.copy2(file_path, txt_path)
            await upload_file(page, txt_path)
        return

    # Confirm the upload
    logger.info("[upload] Step 4/5: Confirming upload...")
    confirm_patterns = [
        re.compile(r"add to chat", re.IGNORECASE),
        re.compile(r"upload", re.IGNORECASE),
        re.compile(r"confirm", re.IGNORECASE),
        re.compile(r"attach", re.IGNORECASE),
        re.compile(r"done", re.IGNORECASE),
    ]
    confirmed = False
    for pattern in confirm_patterns:
        try:
            btn = page.locator("button").filter(has_text=pattern).first
            if await btn.is_visible(timeout=1000):
                logger.info(
                    "[upload] Step 4/5: Clicked confirm button matching '%s'",
                    pattern.pattern,
                )
                await btn.click()
                confirmed = True
                break
        except Exception:
            continue

    if not confirmed:
        logger.info("[upload] Step 4/5: No confirm button found — pressing Escape")
        await page.keyboard.press("Escape")

    await page.wait_for_timeout(2000)

    # Verify attachment
    logger.info("[upload] Step 5/5: Verifying attachment visibility...")
    file_visible = await page.evaluate(
        """(name) => {
            const body = document.body.innerText;
            const baseName = name.replace(/\\.[^.]+$/, "");
            return body.toLowerCase().includes(name.toLowerCase()) ||
                   body.toLowerCase().includes(baseName.toLowerCase());
        }""",
        filename,
    )
    if file_visible:
        logger.info("[upload] Step 5/5: File '%s' confirmed visible in UI", filename)
    else:
        logger.warning(
            "[upload] Step 5/5: File '%s' NOT visible in UI — may not have attached",
            filename,
        )


async def auto_fill_and_submit(page: Page, config: HarnessConfig | None = None) -> bool:
    """Auto-fill visible forms and click Submit. Returns True if form was submitted."""
    form_submit_btn = page.locator(
        'button:has-text("Submit"), button:has-text("Continue"), button:has-text("Confirm Theme"), button:has-text("Confirm")'
    ).first
    try:
        form_visible = await form_submit_btn.is_visible(timeout=3000)
    except Exception:
        return False
    if not form_visible:
        return False

    logger.info(
        "[auto_fill] Form detected — auto-filling (user agent didn't provide actions)"
    )

    # Fill selects with first non-placeholder option
    selects = page.locator("main select")
    select_count = await selects.count()
    if select_count > 0:
        logger.info("[auto_fill] Filling %d select element(s)...", select_count)
    for i in range(select_count):
        sel = selects.nth(i)
        try:
            current_val = await sel.input_value()
        except Exception:
            continue
        if not current_val or current_val == "Select an option...":
            options = await sel.locator("option").all_text_contents()
            first_real = next(
                (o for o in options if o != "Select an option..." and o.strip()),
                None,
            )
            if first_real:
                await sel.select_option(label=first_real)
                logger.info("[auto_fill]   Select #%d -> %r", i + 1, first_real)

    # Fill empty text inputs with placeholder text
    inputs = page.locator('main input[type="text"], main input:not([type])')
    input_count = await inputs.count()
    filled_inputs = 0
    for i in range(input_count):
        inp = inputs.nth(i)
        try:
            val = await inp.input_value()
        except Exception:
            continue
        if not val:
            placeholder = await inp.get_attribute("placeholder") or "General audience"
            await inp.fill(placeholder)
            filled_inputs += 1
    if filled_inputs > 0:
        logger.info("[auto_fill] Filled %d empty text input(s)", filled_inputs)

    # Select first radio button if none selected
    radios = page.locator('main input[type="radio"]')
    if await radios.count() > 0:
        any_checked = await page.locator('main input[type="radio"]:checked').count()
        if any_checked == 0:
            logger.info("[auto_fill] No radio selected — checking first option")
            label = radios.first.locator("xpath=ancestor::label")
            try:
                if await label.is_visible(timeout=2000):
                    await label.click(force=True)
                else:
                    await radios.first.check(force=True)
            except Exception:
                await radios.first.check(force=True)

    await page.wait_for_timeout(500)
    logger.info("[auto_fill] Clicking submit button...")
    await form_submit_btn.click()
    logger.info("[auto_fill] Form submitted")
    return True
