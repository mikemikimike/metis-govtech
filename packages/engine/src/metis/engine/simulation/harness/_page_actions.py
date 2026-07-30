"""Browser interactions — send messages, upload files, fill forms."""

import logging
import re
import shutil
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page

from ._auth import dismiss_modals
from ._config import HarnessConfig
from ._types import UIState
from ._ui_capture import capture_ui_state

logger = logging.getLogger(__name__)


def send_message(
    page: Page,
    message: str,
    config: HarnessConfig,
    timeout_override: int | None = None,
) -> UIState:
    """Send a message in the chat and wait for the full response."""
    timeout = timeout_override or config.timeouts.response_wait_ms
    msg_preview = message[:80] + ("..." if len(message) > 80 else "")
    logger.info("[send_message] Sending: %r (timeout=%dms)", msg_preview, timeout)

    # Snapshot pre-state (placeholder + message count)
    logger.debug("[send_message] Capturing pre-state snapshot...")
    pre_state = page.evaluate("""() => {
        const textarea = document.querySelector("textarea");
        const placeholder = textarea?.getAttribute("placeholder") || "";
        const sel = '[class*="message"], [class*="Message"], ' +
          '[class*="response"], [class*="Response"], ' +
          '[class*="assistant"], [class*="Assistant"]';
        const messages = document.querySelectorAll(sel);
        return { placeholder, messageCount: messages.length };
    }""")
    logger.debug(
        "[send_message] Pre-state: placeholder=%r, messageCount=%d",
        pre_state["placeholder"],
        pre_state["messageCount"],
    )

    # Find and fill the textarea
    input_el = page.locator("textarea").first
    if not input_el.is_visible(timeout=2000):
        logger.info(
            "[send_message] Textarea not visible — trying fallback selectors..."
        )
        try:
            page.get_by_placeholder(
                re.compile(r"ask anything|reply", re.IGNORECASE)
            ).click(timeout=5000)
        except Exception:
            page.locator(
                '[class*="input"], [class*="Input"], [class*="chat"] >> visible=true'
            ).first.click(timeout=3000)
        page.wait_for_timeout(1000)
        input_el = page.locator("textarea").first
        input_el.wait_for(state="visible", timeout=5000)

    logger.info("[send_message] Filling textarea and pressing Enter...")
    input_el.fill(message)
    input_el.press("Enter")

    # Wait for response using dual-condition approach
    logger.info("[send_message] Waiting for response (initial 3s buffer)...")
    page.wait_for_timeout(3000)
    placeholder_already_reply = "Reply" in pre_state["placeholder"]

    logger.info(
        "[send_message] Waiting for new message or placeholder change (timeout=%dms)...",
        timeout,
    )
    page.wait_for_function(
        """({ prevCount, alreadyReply }) => {
            const textarea = document.querySelector("textarea");
            if (!textarea) return false;
            const currentPlaceholder =
              textarea.getAttribute("placeholder") || "";
            const sel = '[class*="message"], [class*="Message"], ' +
              '[class*="response"], [class*="Response"], ' +
              '[class*="assistant"], [class*="Assistant"]';
            const messages = document.querySelectorAll(sel);
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
    logger.info(
        "[send_message] Response detected — polling for processing completion..."
    )

    # Poll for processing completion
    poll_deadline = time.time() * 1000 + 300000
    poll_count = 0
    while time.time() * 1000 < poll_deadline:
        still_processing = page.evaluate("""() => {
            const spinSel = '[class*="loading"], ' +
              '[class*="spinner"], [class*="animate-spin"]';
            const hasSpinner =
              document.querySelector(spinSel) !== null;
            const typeSel =
              '[class*="typing"], [class*="streaming"]';
            const hasTyping =
              document.querySelector(typeSel) !== null;
            const buttons =
              Array.from(document.querySelectorAll('button'));
            const hasStop = buttons.some(
              b => b.textContent?.includes('Stop generating'));
            return hasSpinner || hasTyping || hasStop;
        }""")
        if not still_processing:
            break
        poll_count += 1
        if poll_count % 5 == 1:
            logger.info("[send_message] Still processing (poll #%d)...", poll_count)
        page.wait_for_timeout(2000)

    if poll_count > 0:
        logger.info("[send_message] Processing complete after %d poll(s)", poll_count)

    # Final buffer for remaining streaming
    logger.debug("[send_message] Final 2s buffer...")
    page.wait_for_timeout(2000)
    logger.info("[send_message] Capturing UI state...")
    return capture_ui_state(page)


def upload_file(page: Page, file_path: Path) -> None:
    """Upload a file via the target system's attach-file flow."""
    filename = file_path.name
    logger.info("[upload] Step 1/5: Starting upload of '%s' (%s)", filename, file_path)

    dismiss_modals(page)

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
        with page.expect_file_chooser(timeout=10000) as fc_info:
            attach_button.click(timeout=5000)
        file_chooser = fc_info.value
        logger.info("[upload] Step 3/5: File chooser opened — setting file...")
    except Exception:
        logger.info(
            "[upload] Step 3/5: File chooser failed — using fallback input[type=file]"
        )

    if file_chooser:
        file_chooser.set_files(str(file_path))
    else:
        # Fallback: find input[type="file"] and set directly
        file_input = page.locator('input[type="file"]').first
        file_input.wait_for(state="attached", timeout=5000)
        file_input.set_input_files(str(file_path))

    page.wait_for_timeout(2000)

    # Check for "Unsupported format" error — retry with .txt extension (once)
    has_unsupported = page.evaluate(
        "() => document.body.innerText.includes('Unsupported format')"
    )
    if has_unsupported and file_path.suffix != ".txt":
        logger.info(
            "[upload] Unsupported format detected — retrying '%s' as .txt", filename
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        tmp_dir = Path(tempfile.mkdtemp())
        txt_path = tmp_dir / file_path.with_suffix(".txt").name
        shutil.copy2(file_path, txt_path)
        upload_file(page, txt_path)
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
            if btn.is_visible(timeout=1000):
                logger.info(
                    "[upload] Step 4/5: Clicked confirm button matching '%s'",
                    pattern.pattern,
                )
                btn.click()
                confirmed = True
                break
        except Exception:
            continue

    if not confirmed:
        logger.info("[upload] Step 4/5: No confirm button found — pressing Escape")
        page.keyboard.press("Escape")

    page.wait_for_timeout(2000)

    # Verify attachment
    logger.info("[upload] Step 5/5: Verifying attachment visibility...")
    file_visible = page.evaluate(
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


def auto_fill_and_submit(page: Page) -> bool:
    """Auto-fill visible forms and click Submit. Returns True if form was submitted."""
    form_submit_btn = page.locator(
        'button:has-text("Submit"), button:has-text("Confirm Theme"), button:has-text("Confirm")'
    ).first
    try:
        form_visible = form_submit_btn.is_visible(timeout=3000)
    except Exception:
        return False
    if not form_visible:
        return False

    logger.info(
        "[auto_fill] Form detected — auto-filling (user agent didn't provide actions)"
    )

    # Fill selects with first non-placeholder option
    selects = page.locator("main select")
    select_count = selects.count()
    if select_count > 0:
        logger.info("[auto_fill] Filling %d select element(s)...", select_count)
    for i in range(select_count):
        sel = selects.nth(i)
        try:
            current_val = sel.input_value()
        except Exception:
            continue
        if not current_val or current_val == "Select an option...":
            options = sel.locator("option").all_text_contents()
            first_real = next(
                (o for o in options if o != "Select an option..." and o.strip()),
                None,
            )
            if first_real:
                sel.select_option(label=first_real)
                logger.info("[auto_fill]   Select #%d -> %r", i + 1, first_real)

    # Fill empty text inputs with placeholder text
    inputs = page.locator('main input[type="text"], main input:not([type])')
    input_count = inputs.count()
    filled_inputs = 0
    for i in range(input_count):
        inp = inputs.nth(i)
        try:
            val = inp.input_value()
        except Exception:
            continue
        if not val:
            placeholder = inp.get_attribute("placeholder") or "General audience"
            inp.fill(placeholder)
            filled_inputs += 1
    if filled_inputs > 0:
        logger.info("[auto_fill] Filled %d empty text input(s)", filled_inputs)

    # Select first radio button if none selected
    radios = page.locator('main input[type="radio"]')
    if radios.count() > 0:
        any_checked = page.locator('main input[type="radio"]:checked').count()
        if any_checked == 0:
            logger.info("[auto_fill] No radio selected — checking first option")
            label = radios.first.locator("xpath=ancestor::label")
            try:
                if label.is_visible(timeout=2000):
                    label.click(force=True)
                else:
                    radios.first.check(force=True)
            except Exception:
                radios.first.check(force=True)

    page.wait_for_timeout(500)
    logger.info("[auto_fill] Clicking submit button...")
    form_submit_btn.click()
    logger.info("[auto_fill] Form submitted")
    return True
