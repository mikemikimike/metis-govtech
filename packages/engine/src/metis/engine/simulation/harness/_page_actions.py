"""Browser interactions — send messages, upload files, fill forms."""

import contextlib
import re
import shutil
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Locator, Page

from metis.core.logging import get_logger

from ..types import UIState
from ._auth import dismiss_modals
from ._config import HarnessConfig
from ._protocol import (
    ActionResult,
    do_action,
    is_page_active,
    stabilize,
    wait_until_settled,
)
from ._ui_capture import capture_ui_state

logger = get_logger()

_FILE_VISIBLE_JS = """(name) => {
    const body = document.body.innerText.toLowerCase();
    const base = name.replace(/\\.[^.]+$/, "").toLowerCase();
    return body.includes(name.toLowerCase()) || body.includes(base);
}"""

# --- Orca-specific selectors (hardcoded from dom-dump-post.json) ---
#
# Chat input placeholder (two variants):
#   Pre-response:  "Ask anything — type / for agents, @ for your library files"
#   Post-response: "Reply, or type / for agents, @ for library files..."
_CHAT_INPUT_PLACEHOLDER = re.compile(
    r"ask anything|reply.*type /|type / for agents", re.IGNORECASE
)

# Container for chat messages — Orca uses <main> (no role="log" exists)
_CHAT_CONTAINER_SELECTOR = "main"

# Message elements: Orca uses exactly these two classes on message wrappers.
# Confirmed from dom-dump-post.json sampleMessageClasses:
#   "message-user"      — user message wrapper
#   "message-assistant" — assistant message wrapper
_MESSAGE_SELECTOR = ".message-user, .message-assistant"


def _find_chat_textarea(page: Page) -> Locator:
    """Find the chat input textarea (not form textareas).

    Orca shows form textareas (e.g. 'keep it under 8 slides') above the
    chat input when agent configuration forms are active. We identify the
    chat input by its known placeholder pattern.
    """
    # Primary: find by placeholder pattern (most reliable)
    chat_input = page.get_by_placeholder(_CHAT_INPUT_PLACEHOLDER).first
    try:
        if chat_input.is_visible(timeout=1000):
            return chat_input
    except Exception:
        pass

    # Fallback: textbox role (may match form fields too)
    textbox = page.get_by_role("textbox").first
    try:
        if textbox.is_visible(timeout=1000):
            return textbox
    except Exception:
        pass

    # Last resort: any textarea
    return page.locator("textarea").last


def _get_chat_text_length(page: Page) -> int:
    """Get the text length of the main chat area.

    Orca has no [role="log"] — main is the chat container.
    Text-length delta is the primary response detection signal.
    """
    try:
        main = page.locator("main")
        if main.count() > 0:
            return len(main.first.inner_text(timeout=2000))
    except Exception:
        pass
    return 0


def _count_chat_messages(page: Page) -> int:
    """Count chat messages using Orca's exact class names.

    From dom-dump-post.json: .message-user and .message-assistant
    are the definitive message wrapper classes.
    """
    try:
        count = page.evaluate("""() => {
            const container = document.querySelector('main') || document.body;
            return container.querySelectorAll('.message-user, .message-assistant').length;
        }""")
        return count
    except Exception:
        return 0


def _wait_for_response(
    page: Page, pre_count: int, pre_text_len: int, timeout_ms: int
) -> bool:
    """Poll until a new response appears. Returns True if detected.

    Detection strategies (in priority order):
    1. Text growth >50 chars in main — universal, works even when agents
       generate responses asynchronously (the primary strategy)
    2. Message count increase — fast early-exit when message elements appear
    3. Chat input placeholder changed to "Reply" — catches the transition
       from initial state to post-first-response state
    """
    poll_ms = 500
    start = time.time()
    deadline = start + timeout_ms / 1000

    while time.time() < deadline:
        # Strategy 1 (primary): text content grew substantially
        current_len = _get_chat_text_length(page)
        if current_len > pre_text_len + 50:
            logger.info(
                "[response] Detected via text growth: %d -> %d (+%d chars, %.0fms)",
                pre_text_len,
                current_len,
                current_len - pre_text_len,
                (time.time() - start) * 1000,
            )
            return True

        # Strategy 2 (fast exit): message count increased
        current_count = _count_chat_messages(page)
        if current_count > pre_count:
            logger.info(
                "[response] Detected via message count: %d -> %d (%.0fms)",
                pre_count,
                current_count,
                (time.time() - start) * 1000,
            )
            return True

        # Strategy 3: chat input placeholder changed to "Reply"
        try:
            chat_input = page.get_by_placeholder(_CHAT_INPUT_PLACEHOLDER).first
            placeholder = chat_input.get_attribute("placeholder") or ""
            if "Reply" in placeholder and pre_text_len == 0:
                logger.info(
                    "[response] Detected via placeholder change (%.0fms)",
                    (time.time() - start) * 1000,
                )
                return True
        except Exception:
            pass

        try:
            page.wait_for_timeout(poll_ms)
        except Exception:
            # Browser context destroyed — page closed or crashed
            logger.warning("[response] Page context lost during polling")
            return False

    logger.warning(
        "[response] NOT detected after %dms (count=%d->%d, text=%d->%d)",
        timeout_ms,
        pre_count,
        _count_chat_messages(page),
        pre_text_len,
        _get_chat_text_length(page),
    )
    return False


_CONFIRM_PATTERNS = [
    re.compile(r"add to chat", re.IGNORECASE),
    re.compile(r"upload", re.IGNORECASE),
    re.compile(r"confirm", re.IGNORECASE),
    re.compile(r"attach", re.IGNORECASE),
    re.compile(r"done", re.IGNORECASE),
]

_ATTACH_SELECTOR = ", ".join(
    [
        'button:has(span.sr-only:has-text("Attach file"))',
        'button:has(span:has-text("Attach file"))',
        'button:has-text("Attach file")',
        'button[aria-label*="attach" i]',
        'button[aria-label*="file" i]',
    ]
)


async def send_message(
    page: Page,
    message: str,
    config: HarnessConfig,
    timeout_override: int | None = None,
) -> UIState:
    """Send a message in the chat and wait for the full response."""
    timeout = timeout_override or config.timeouts.response_wait_ms
    msg_preview = message[:80] + ("..." if len(message) > 80 else "")
    logger.info("[send_message] Sending: %r (timeout=%dms)", msg_preview, timeout)

    # Snapshot pre-state: text length (primary) + message count (secondary)
    pre_text_len = _get_chat_text_length(page)
    pre_count = _count_chat_messages(page)
    logger.debug(
        "[send_message] Pre-state: text_len=%d, message_count=%d",
        pre_text_len,
        pre_count,
    )

    # Find the CHAT textarea (not form textareas that may appear above it)
    input_el = _find_chat_textarea(page)
    try:
        visible = input_el.is_visible(timeout=2000)
    except Exception:
        visible = False
    if not visible:
        logger.info("[send_message] Chat textarea not visible — trying fallback...")
        try:
            page.get_by_placeholder(_CHAT_INPUT_PLACEHOLDER).click(timeout=5000)
        except Exception:
            try:
                page.get_by_role("textbox").last.click(timeout=3000)
            except Exception:
                logger.warning("[send_message] No textbox found at all")
                return capture_ui_state(page)
        stabilize(page, "input focus after fallback click", 1000)
        input_el = _find_chat_textarea(page)
        try:
            input_el.wait_for(state="visible", timeout=5000)
        except Exception:
            logger.warning("[send_message] Chat input never appeared")
            return capture_ui_state(page)

    # Ensure Orca isn't mid-generation before we send (avoids "Response cancelled")
    if is_page_active(page):
        logger.info("[send_message] Page still active — waiting before sending...")
        wait_until_settled(page, idle_timeout_ms=30000)

    # Send the message — single type() call avoids stale element between fill/press
    send_result = do_action(
        page,
        intent=f"send message: {msg_preview}",
        act=lambda: input_el.type(message + "\n", delay=0),
    )
    if not send_result.succeeded:
        logger.warning("[send_message] type() failed — not waiting for response")
        return capture_ui_state(page)

    # Wait for response (text-delta primary, message-count secondary)
    response_detected = _wait_for_response(page, pre_count, pre_text_len, timeout)

    if not response_detected:
        # Check if a dialog appeared during the wait — dismiss and retry
        try:
            dialog = page.get_by_role("dialog")
            if dialog.count() > 0 and dialog.first.is_visible():
                logger.info(
                    "[send_message] Dialog appeared during wait — dismissing and retrying..."
                )
                dismiss_modals(page)
                stabilize(page, "post-dialog-dismiss", 1000)
                response_detected = _wait_for_response(
                    page, pre_count, pre_text_len, min(timeout, 60000)
                )
        except Exception:
            pass
        if not response_detected:
            logger.warning(
                "[send_message] Response did not appear within %dms", timeout
            )

    # Wait for processing to complete — keeps waiting while page is active
    wait_until_settled(page)

    # Check for "Response cancelled" — means we interrupted Orca mid-generation.
    # Wait for the real response that follows the cancellation.
    try:
        last_msg = page.locator("main .message-assistant").last
        if last_msg.count() > 0:
            text = last_msg.inner_text(timeout=2000).strip()
            if text.lower() in ("response cancelled", "response cancelled."):
                logger.info(
                    "[send_message] Detected 'Response cancelled' — waiting for real response..."
                )
                new_text_len = _get_chat_text_length(page)
                _wait_for_response(page, pre_count, new_text_len, min(timeout, 120000))
                wait_until_settled(page)
    except Exception:
        pass

    logger.info("[send_message] Capturing UI state...")
    return await capture_ui_state(page)


def _execute_upload_flow(page: Page, file_path: Path) -> None:
    """Raw upload mechanics — click attach, set file, confirm. No waits."""
    dismiss_modals(page)

    attach_button = page.locator(_ATTACH_SELECTOR).first

    # Trigger file chooser
    file_chooser = None
    try:
        with page.expect_file_chooser(timeout=10000) as fc_info:
            attach_button.click(timeout=5000)
        file_chooser = fc_info.value
        logger.info("[upload] File chooser opened — setting file...")
    except Exception:
        logger.info("[upload] File chooser failed — using fallback input[type=file]")

    if file_chooser:
        await file_chooser.set_files(str(file_path))
    else:
        try:
            file_input = page.locator('input[type="file"]').first
            file_input.wait_for(state="attached", timeout=5000)
            file_input.set_input_files(str(file_path))
        except Exception as exc:
            raise RuntimeError(f"Cannot set upload file: {exc}") from exc

    # Check for "Unsupported format" error — retry with .txt extension
    try:
        has_unsupported = page.evaluate(
            """() => {
                const alerts = document.querySelectorAll('[role="alert"]');
                return Array.from(alerts).some(el => el.innerText.includes('Unsupported format'))
                    || document.body.innerText.includes('Unsupported format');
            }"""
        )
    except Exception:
        has_unsupported = False
    if has_unsupported and file_path.suffix != ".txt":
        logger.info(
            "[upload] Unsupported format detected — retrying '%s' as .txt",
            file_path.name,
        )
        with contextlib.suppress(Exception):
            page.keyboard.press("Escape")
        stabilize(page, "escape unsupported-format dialog", 500)
        with tempfile.TemporaryDirectory() as tmp_dir:
            txt_path = Path(tmp_dir) / file_path.with_suffix(".txt").name
            shutil.copy2(file_path, txt_path)
            _execute_upload_flow(page, txt_path)

    # Click confirm button if visible
    for pattern in _CONFIRM_PATTERNS:
        try:
            btn = page.locator("button").filter(has_text=pattern).first
            if await btn.is_visible(timeout=1000):
                logger.info(
                    "[upload] Clicked confirm button matching '%s'", pattern.pattern
                )
                btn.click()
                break
        except Exception:
            continue


def upload_file(page: Page, file_path: Path) -> ActionResult:
    """Upload a file via the target system's attach-file flow.

    Returns ActionResult with effect_verified indicating whether the file
    chip appeared in the UI after upload.
    """
    filename = file_path.name
    return do_action(
        page,
        intent=f"upload '{filename}'",
        act=lambda: _execute_upload_flow(page, file_path),
        verify=_FILE_VISIBLE_JS,
        verify_args=filename,
        verify_timeout_ms=5000,
    )


async def auto_fill_and_submit(page: Page) -> bool:
    """Auto-fill visible forms and click Submit. Returns True if form was submitted."""
    form_submit_btn = page.locator(
        'button:has-text("Submit"), '
        'button:has-text("Continue"), '
        'button:has-text("Confirm Theme"), '
        'button:has-text("Confirm")'
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

    # Fill selects with first non-placeholder option — re-query after each
    # because filling one select can trigger conditional form logic
    try:
        select_count = page.locator("main select").count()
    except Exception:
        select_count = 0
    if select_count > 0:
        logger.info("[auto_fill] Filling %d select element(s)...", select_count)
    for i in range(select_count):
        try:
            selects = page.locator("main select")
            if i >= selects.count():
                break
            sel = selects.nth(i)
            current_val = sel.input_value()
            if not current_val or current_val == "Select an option...":
                options = sel.locator("option").all_text_contents()
                first_real = next(
                    (o for o in options if o != "Select an option..." and o.strip()),
                    None,
                )
                if first_real:
                    sel.select_option(label=first_real)
                    logger.info("[auto_fill]   Select #%d -> %r", i + 1, first_real)
                    stabilize(page, "form update after select change", 300)
        except Exception:
            continue

    # Fill empty text inputs with placeholder text — re-query each iteration
    try:
        input_count = page.locator(
            'main input[type="text"], main input:not([type])'
        ).count()
    except Exception:
        input_count = 0
    filled_inputs = 0
    for i in range(input_count):
        try:
            inputs = page.locator('main input[type="text"], main input:not([type])')
            if i >= inputs.count():
                break
            inp = inputs.nth(i)
            val = inp.input_value()
            if not val:
                placeholder = inp.get_attribute("placeholder") or "General audience"
                inp.fill(placeholder)
                filled_inputs += 1
                stabilize(page, "form update after input fill", 200)
        except Exception:
            continue
    if filled_inputs > 0:
        logger.info("[auto_fill] Filled %d empty text input(s)", filled_inputs)

    # Select first radio button if none selected
    try:
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
                    with contextlib.suppress(Exception):
                        radios.first.check(force=True)
    except Exception:
        pass

    stabilize(page, "form values committed before submit", 500)
    logger.info("[auto_fill] Clicking submit button...")
    try:
        form_submit_btn.click()
    except Exception as exc:
        logger.warning("[auto_fill] Submit click failed: %s", exc)
        return False
    logger.info("[auto_fill] Form submitted")
    return True
