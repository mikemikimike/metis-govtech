"""UI state extraction — captures response text, artifacts, forms, errors.

All selectors are hardcoded from Orca DOM dumps (2026-08-11).
No class-guessing heuristics — only tag-based, role-based, and text-based
selectors that map to Orca's actual DOM structure.
"""

import re
from pathlib import Path

from playwright.async_api import Page

from metis.core.logging import get_logger

from ..types import Artifact, FormElement, UIState
from ._protocol import stabilize

logger = get_logger()

_FOOTER_PATTERNS = re.compile(
    r"Reply, or type|Use Orca only|Conversations are kept|Ask anything"
)

_CHAT_INPUT_PLACEHOLDER = re.compile(
    r"ask anything|reply.*type /|type / for agents|generating response",
    re.IGNORECASE,
)

_NAV_BUTTON_PATTERNS = re.compile(
    r"new chat|collapse sidebar|expand sidebar|conversation options"
    r"|copy|share|send message|attach file|upload|/agents"
    r"|open files panel|remove |reasoning",
    re.IGNORECASE,
)


def _extract_response_text(page: Page) -> str:
    """Extract the last assistant response text.

    Uses .message-assistant (exact Orca class from DOM dump).
    Falls back to main inner_text trimmed at footer patterns.
    """
    try:
        messages = page.locator("main .message-assistant")
        count = messages.count()
        if count > 0:
            text = messages.nth(count - 1).inner_text(timeout=3000).strip()
            if len(text) > 10:
                return text
    except Exception:
        pass

    main = page.locator("main")
    if main.count() > 0:
        try:
            text = main.first.inner_text(timeout=3000)
            match = _FOOTER_PATTERNS.search(text)
            if match:
                text = text[: match.start()].strip()
            paragraphs = [p for p in text.split("\n") if p.strip()]
            if paragraphs:
                return "\n".join(paragraphs[-20:])
        except Exception:
            pass

    return ""


def _extract_artifacts(page: Page) -> list[dict]:
    """Detect downloadable artifacts using tag-based selectors."""
    artifacts: list[dict] = []
    seen_names: set[str] = set()

    def _add(name: str, url: str | None = None) -> None:
        if name and name not in seen_names and len(name) < 200:
            seen_names.add(name)
            artifacts.append({"name": name, "type": "download", "url": url})

    # a[download] links
    download_links = page.locator("main a[download]")
    for i in range(download_links.count()):
        try:
            el = download_links.nth(i)
            name = el.get_attribute("download") or el.inner_text(timeout=1000).strip()
            url = el.get_attribute("href")
            _add(name or "file", url)
        except Exception:
            continue

    # Blob links
    blob_links = page.locator('main a[href^="blob:"]')
    for i in range(blob_links.count()):
        try:
            el = blob_links.nth(i)
            name = (
                el.get_attribute("download")
                or el.inner_text(timeout=1000).strip()
                or "blob-file"
            )
            _add(name, el.get_attribute("href"))
        except Exception:
            continue

    # File-extension links
    file_ext_re = re.compile(
        r"\.(csv|xlsx|xls|pdf|pptx|ppt|png|jpg|jpeg|json|html|zip|docx|py)(\?|$)",
        re.IGNORECASE,
    )
    all_links = page.locator("main a[href]")
    for i in range(all_links.count()):
        try:
            el = all_links.nth(i)
            href = el.get_attribute("href") or ""
            if el.get_attribute("download") is not None:
                continue
            if file_ext_re.search(href):
                name = el.inner_text(timeout=1000).strip()
                if not name:
                    name = href.split("/")[-1].split("?")[0]
                _add(name or "file", href)
        except Exception:
            continue

    # NOTE: Orca's "Download <filename>" buttons are file-viewer triggers for
    # already-uploaded files, not real artifact downloads. Real artifacts are
    # always <a> links with href/download attributes. No button detection needed.

    return artifacts


def _extract_errors(page: Page) -> list[str]:
    """Detect error messages via role="alert"."""
    errors: list[str] = []
    alert_els = page.locator('main [role="alert"]')
    for i in range(alert_els.count()):
        try:
            text = alert_els.nth(i).inner_text(timeout=1000).strip()
            if text and len(text) < 500 and text not in errors:
                errors.append(text)
        except Exception:
            continue
    return errors


def _extract_interactive_elements(page: Page) -> list[str]:
    """Detect actionable buttons the agent might need to click.

    Ignores navigation/chrome buttons (send, attach, new chat, etc.)
    and only surfaces buttons that represent interactive choices within
    the conversation (suggestion chips, action buttons from the assistant).
    """
    elements: set[str] = set()

    buttons = page.locator("main button")
    for i in range(buttons.count()):
        try:
            el = buttons.nth(i)
            if not el.is_visible(timeout=500):
                continue
            text = el.inner_text(timeout=1000).strip()
            if not text or len(text) > 100:
                continue
            if _NAV_BUTTON_PATTERNS.search(text):
                continue
            # Skip "Stop generating" — it's an activity indicator, not a choice
            if "stop generating" in text.lower():
                continue
            elements.add(text)
        except Exception:
            continue

    return list(elements)


def _extract_form_elements(page: Page) -> list[dict]:
    """Extract form controls using tag-based selectors.

    Orca uses standard HTML form elements: <select>, <input>, <textarea>,
    <button type="submit">. No custom web components.
    """
    form_elements: list[dict] = []

    # Selects
    selects = page.locator("main select")
    for i in range(selects.count()):
        try:
            el = selects.nth(i)
            label = el.get_attribute("aria-label") or el.get_attribute("name") or ""
            options = el.evaluate(
                """el => Array.from(el.options).map(o => o.text.trim()).filter(Boolean)"""
            )
            selected = el.evaluate(
                """el => el.options[el.selectedIndex]?.text.trim() || el.value || null"""
            )
            selector = _build_selector(el, "select", i)
            form_elements.append(
                {
                    "type": "select",
                    "label": label,
                    "selector": selector,
                    "value": selected,
                    "options": options if options else None,
                }
            )
        except Exception:
            continue

    # Text inputs (not hidden/file/radio/checkbox)
    inputs = page.locator(
        'main input:not([type="radio"]):not([type="checkbox"])'
        ':not([type="file"]):not([type="hidden"])'
    )
    for i in range(inputs.count()):
        try:
            el = inputs.nth(i)
            label = (
                el.get_attribute("aria-label")
                or el.get_attribute("placeholder")
                or el.get_attribute("name")
                or ""
            )
            selector = _build_selector(el, "input", i)
            form_elements.append(
                {
                    "type": "input",
                    "label": label,
                    "selector": selector,
                    "value": el.input_value(timeout=1000) or None,
                    "placeholder": el.get_attribute("placeholder"),
                }
            )
        except Exception:
            continue

    # Textareas (excluding the main chat input)
    textareas = page.locator("main textarea")
    for i in range(textareas.count()):
        try:
            el = textareas.nth(i)
            placeholder = el.get_attribute("placeholder") or ""
            if _CHAT_INPUT_PLACEHOLDER.search(placeholder):
                continue
            label = el.get_attribute("aria-label") or placeholder or ""
            selector = _build_selector(el, "textarea", i)
            form_elements.append(
                {
                    "type": "textarea",
                    "label": label,
                    "selector": selector,
                    "value": el.input_value(timeout=1000) or None,
                    "placeholder": placeholder or None,
                }
            )
        except Exception:
            continue

    # Radio groups
    radios = page.locator('main input[type="radio"]')
    radio_count = radios.count()
    if radio_count > 0:
        groups: dict[str, list] = {}
        for i in range(radio_count):
            try:
                el = radios.nth(i)
                name = el.get_attribute("name") or f"radio-{i}"
                if name not in groups:
                    groups[name] = []
                groups[name].append(el)
            except Exception:
                continue
        for name, els in groups.items():
            try:
                options = []
                checked_value = None
                for el in els:
                    val = el.get_attribute("value") or ""
                    lbl = el.get_attribute("aria-label") or val
                    options.append(lbl)
                    if el.is_checked():
                        checked_value = lbl
                selector = f'input[type="radio"][name="{name}"]'
                form_elements.append(
                    {
                        "type": "radio",
                        "label": name,
                        "selector": selector,
                        "value": checked_value,
                        "options": options if options else None,
                        "checked": checked_value is not None,
                    }
                )
            except Exception:
                continue

    # Checkboxes
    checkboxes = page.locator('main input[type="checkbox"]')
    for i in range(checkboxes.count()):
        try:
            el = checkboxes.nth(i)
            label = el.get_attribute("aria-label") or el.get_attribute("name") or ""
            selector = _build_selector(el, 'input[type="checkbox"]', i)
            form_elements.append(
                {
                    "type": "checkbox",
                    "label": label,
                    "selector": selector,
                    "checked": el.is_checked(),
                    "value": el.get_attribute("value"),
                }
            )
        except Exception:
            continue

    # Form action buttons (Submit, Cancel, etc.)
    _FORM_BUTTON_RE = re.compile(
        r"^(submit|confirm|apply|generate|create|start|run|save"
        r"|ok|yes|no|cancel|clear|reset|search|analyze|proceed|continue)$",
        re.IGNORECASE,
    )
    buttons = page.locator("main button")
    for i in range(buttons.count()):
        try:
            el = buttons.nth(i)
            btn_type = el.get_attribute("type") or ""
            text = el.inner_text(timeout=1000).strip()
            if not text or len(text) > 100:
                continue
            is_form_button = btn_type == "submit" or _FORM_BUTTON_RE.match(text)
            if not is_form_button:
                continue
            selector = f'button:has-text("{text}")'
            form_elements.append(
                {"type": "button", "label": text, "selector": selector}
            )
        except Exception:
            continue

    return form_elements


def _build_selector(el, tag: str, index: int) -> str:  # noqa: ANN001
    """Build a stable CSS selector for a form element."""
    try:
        el_id = el.get_attribute("id")
        if el_id:
            return f"#{el_id}"
        name = el.get_attribute("name")
        if name:
            return f'{tag}[name="{name}"]'
        aria_label = el.get_attribute("aria-label")
        if aria_label:
            return f'{tag}[aria-label="{aria_label}"]'
    except Exception:
        pass
    return f"main {tag}:nth-of-type({index + 1})"


def _extract_status_labels(page: Page) -> list[str]:
    """Detect processing-status labels shown by agent tools.

    In Orca, these appear as text like "Searching...", "Analyzing...",
    "Running code..." inside the message-assistant container.
    """
    labels: list[str] = []
    status_re = re.compile(
        r"(working|processing|generating|analyzing|thinking|running|searching)",
        re.IGNORECASE,
    )
    try:
        messages = page.locator("main .message-assistant")
        count = messages.count()
        if count > 0:
            last_msg = messages.nth(count - 1)
            # Look for short text nodes that match status patterns
            spans = last_msg.locator("span, p, div")
            for i in range(min(spans.count(), 50)):
                try:
                    text = spans.nth(i).inner_text(timeout=500).strip()
                    if (
                        text
                        and 3 < len(text) < 100
                        and status_re.search(text)
                        and text not in labels
                    ):
                        labels.append(text)
                except Exception:
                    continue
    except Exception:
        pass
    return labels


def capture_ui_state(page: Page) -> UIState:
    """Extract the current UI state from the page.

    All detection uses Playwright locators with hardcoded Orca selectors.
    No class-guessing JS blobs.
    """
    logger.debug("[ui_capture] Extracting response text...")
    response_text = _extract_response_text(page)

    logger.debug("[ui_capture] Extracting artifacts...")
    artifacts = _extract_artifacts(page)

    logger.debug("[ui_capture] Extracting errors...")
    errors = _extract_errors(page)

    logger.debug("[ui_capture] Extracting interactive elements...")
    interactive = _extract_interactive_elements(page)

    logger.debug("[ui_capture] Extracting form elements...")
    forms = _extract_form_elements(page)

    logger.debug("[ui_capture] Extracting status labels...")
    status_labels = _extract_status_labels(page)

    state = UIState(
        text=response_text,
        artifacts=[Artifact.model_validate(a) for a in artifacts],
        target_status_labels=status_labels,
        errors=errors,
        interactive_elements=interactive,
        form_elements=[FormElement.model_validate(f) for f in forms],
    )
    logger.debug(
        "[ui_capture] Captured: text=%d chars, artifacts=%d, forms=%d, errors=%d, labels=%d",
        len(state.text),
        len(state.artifacts),
        len(state.form_elements),
        len(state.errors),
        len(state.target_status_labels),
    )
    return state


async def capture_artifacts_panel(page: Page) -> list[Artifact]:
    """Open More/panel buttons and scan for downloadable artifacts."""
    logger.debug("[artifacts_panel] Scanning for artifacts...")

    # Try "Open files panel" button (Orca-specific, from DOM dump)
    files_btn = page.get_by_role("button", name="Open files panel")
    if files_btn.count() > 0:
        try:
            if files_btn.first.is_visible(timeout=1000):
                files_btn.first.click()
                logger.debug("[artifacts_panel] Opened files panel")
                stabilize(page, "files panel expand", 1500)
        except Exception:
            pass

    # Fallback: generic panel triggers
    sidebar_triggers = [
        page.locator('button[aria-label*="artifact" i]').first,
        page.locator('button[aria-label*="panel" i]').first,
    ]
    for trigger in sidebar_triggers:
        try:
            if await trigger.is_visible(timeout=1000):
                await trigger.click()
                logger.debug("[artifacts_panel] Opened sidebar via header icon")
                stabilize(page, "sidebar panel expand", 1500)
                break
        except Exception:
            continue

    # Scan full page for download links (tag-based selectors only)
    artifacts: list[Artifact] = []
    seen: set[str] = set()

    download_links = page.locator(
        'a[download], a[href^="blob:"], '
        'a[href*=".csv"], a[href*=".xlsx"], a[href*=".pdf"], '
        'a[href*=".pptx"], a[href*=".png"], a[href*=".json"], '
        'a[href*=".py"], a[href*=".html"], a[href*=".zip"]'
    )
    for i in range(download_links.count()):
        try:
            el = download_links.nth(i)
            name = (
                el.get_attribute("download")
                or el.inner_text(timeout=1000).strip()
                or (el.get_attribute("href") or "").split("/")[-1].split("?")[0]
                or "file"
            )
            if name in seen or len(name) > 200:
                continue
            seen.add(name)
            artifacts.append(
                Artifact(name=name, type="download", url=el.get_attribute("href"))
            )
        except Exception:
            continue

    # "Download" buttons
    buttons = page.locator("button")
    for i in range(buttons.count()):
        try:
            text = buttons.nth(i).inner_text(timeout=1000).strip()
            if (
                re.match(r"download", text, re.IGNORECASE)
                and len(text) < 60
                and text not in seen
            ):
                seen.add(text)
                artifacts.append(Artifact(name=text, type="download"))
        except Exception:
            continue

    # Close any open panel
    page.keyboard.press("Escape")
    stabilize(page, "menu close after Escape", 500)

    if artifacts:
        logger.info(
            "[artifacts_panel] Found %d artifact(s): %s",
            len(artifacts),
            ", ".join(a.name for a in artifacts[:5]),
        )
    else:
        logger.debug("[artifacts_panel] No artifacts found")
    return artifacts


def capture_inline_charts(page: Page, output_dir: Path, turn: int = 0) -> list[dict]:
    """Screenshot inline chart/SVG/canvas elements as PNG files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    chart_index = 0

    locator_specs = [
        "svg:has(rect):has(text), svg:has(path):has(g)",
        "canvas",
    ]

    for spec in locator_specs:
        elements = page.locator(f"main {spec}")
        count = elements.count()
        for i in range(count):
            try:
                el = elements.nth(i)
                if await el.is_visible(timeout=1000):
                    box = await el.bounding_box()
                    if box and box["width"] > 100 and box["height"] > 50:
                        chart_index += 1
                        filename = f"turn-{turn}-chart-{chart_index}.png"
                        out_path = output_dir / filename
                        await el.screenshot(path=str(out_path))
                        results.append({"filename": filename, "path": str(out_path)})
                        logger.debug(
                            "[charts] Captured chart #%d: %dx%d -> %s",
                            chart_index,
                            int(box["width"]),
                            int(box["height"]),
                            filename,
                        )
            except Exception:
                continue

    if results:
        logger.info(
            "[charts] Captured %d inline chart(s) as PNG to %s",
            len(results),
            output_dir,
        )
    return results
