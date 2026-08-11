"""UI state extraction — captures response text, artifacts, forms, errors."""

from pathlib import Path

from playwright.async_api import Page

from metis.core.logging import get_logger

from ..types import Artifact, UIState
from ._config import RetryConfig
from ._retry import action_retry

logger = get_logger()

_CAPTURE_UI_STATE_JS = """() => {
    const main = document.querySelector("main") || document.body;
    const allText = main.innerText;
    let responseText = "";

    const messageBlocks = main.querySelectorAll(
      '[class*="message"], [class*="Message"], [class*="response"], [class*="Response"], [class*="assistant"], [class*="Assistant"]'
    );

    if (messageBlocks.length > 0) {
      const lastBlock = messageBlocks[messageBlocks.length - 1];
      responseText = lastBlock.innerText?.trim() || "";
    }

    if (!responseText) {
      const textarea = document.querySelector("textarea");
      if (textarea) {
        const cutoffs = ["Reply, or type", "Use Orca only", "Conversations are kept"];
        let text = allText;
        for (const cutoff of cutoffs) {
          const idx = text.indexOf(cutoff);
          if (idx > 0) { text = text.slice(0, idx).trim(); }
        }
        const paragraphs = text.split("\\n").filter(p => p.trim().length > 0);
        if (paragraphs.length > 0) {
          responseText = paragraphs.slice(-10).join("\\n");
        }
      }
    }

    const artifacts = [];
    const downloadLinks = main.querySelectorAll("a[download]");
    downloadLinks.forEach(link => {
      artifacts.push({
        name: link.download || link.textContent?.trim() || "file",
        type: "download",
        url: link.href || undefined,
      });
    });

    const fileExtPattern = /\\.(csv|xlsx|xls|pdf|pptx|ppt|png|jpg|jpeg|json|html|zip|docx)(\\?|$)/i;
    const allAnchors = main.querySelectorAll("a[href]");
    allAnchors.forEach(link => {
      if (link.hasAttribute("download")) return;
      const href = link.href || "";
      if (fileExtPattern.test(href) || href.startsWith("blob:")) {
        const name = link.textContent?.trim() || href.split("/").pop()?.split("?")[0] || "file";
        artifacts.push({ name, type: "download", url: href });
      }
    });

    const downloadButtons = main.querySelectorAll("button");
    downloadButtons.forEach(btn => {
      const text = btn.textContent?.trim() || "";
      if (/^download\\b/i.test(text) && text.length < 60) {
        artifacts.push({ name: text, type: "download" });
      }
    });

    const agentLabels = [];
    const statusPatterns = ["working", "processing", "generating", "analyzing", "thinking", "running", "searching"];
    const allElements = main.querySelectorAll("*");
    allElements.forEach(el => {
      const text = el.textContent?.trim().toLowerCase() || "";
      if (text.length < 100 && text.length > 3 && statusPatterns.some(p => text.includes(p))) {
        if (el.children.length <= 2 && el.innerText?.trim()) {
          agentLabels.push(el.innerText.trim());
        }
      }
    });
    const uniqueLabels = [...new Set(agentLabels)];

    const errors = [];
    const errorElements = main.querySelectorAll('[class*="error"], [class*="Error"], [role="alert"], [class*="alert"], [class*="Alert"]');
    errorElements.forEach(el => {
      const text = el.innerText?.trim();
      if (text && text.length > 0 && text.length < 500) { errors.push(text); }
    });
    const redElements = main.querySelectorAll('[style*="color: red"], [style*="color:red"], [style*="color: #f"], [style*="color:#f"]');
    redElements.forEach(el => {
      const text = el.innerText?.trim();
      if (text && text.length > 0 && text.length < 500 && !errors.includes(text)) { errors.push(text); }
    });

    const interactiveElements = [];
    const interactiveButtons = main.querySelectorAll('button:not([class*="send"]):not([class*="Send"])');
    interactiveButtons.forEach(btn => {
      const text = btn.textContent?.trim();
      if (text && text.length > 0 && text.length < 100
          && !text.toLowerCase().includes("new chat")
          && !text.toLowerCase().includes("copy")
          && !text.toLowerCase().includes("share")) {
        interactiveElements.push(text);
      }
    });
    const chips = main.querySelectorAll('[class*="chip"], [class*="Chip"], [class*="suggestion"], [class*="Suggestion"], [class*="option"], [class*="Option"]');
    chips.forEach(chip => {
      const text = chip.textContent?.trim();
      if (text && text.length > 0 && text.length < 200) { interactiveElements.push(text); }
    });

    const formElements = [];
    const getSelectorFor = (el) => {
      if (el.id) return "#" + CSS.escape(el.id);
      const nameAttr = el.getAttribute("name");
      if (nameAttr) return el.tagName.toLowerCase() + '[name="' + nameAttr + '"]';
      const ariaLabel = el.getAttribute("aria-label");
      if (ariaLabel) return el.tagName.toLowerCase() + '[aria-label="' + ariaLabel + '"]';
      const parent = el.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
        const idx = siblings.indexOf(el) + 1;
        const parentSel = getSelectorFor(parent);
        return parentSel + " > " + el.tagName.toLowerCase() + ":nth-of-type(" + idx + ")";
      }
      return el.tagName.toLowerCase();
    };

    const getLabelFor = (el) => {
      if (el.id) {
        const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (lbl) return lbl.innerText.trim();
      }
      const wrappingLabel = el.closest("label");
      if (wrappingLabel) {
        const clone = wrappingLabel.cloneNode(true);
        const inputInClone = clone.querySelector("input, select, textarea");
        if (inputInClone) inputInClone.remove();
        const text = clone.innerText.trim();
        if (text) return text;
      }
      const ariaLabel = el.getAttribute("aria-label");
      if (ariaLabel) return ariaLabel;
      const labelledBy = el.getAttribute("aria-labelledby");
      if (labelledBy) {
        const lblEl = document.getElementById(labelledBy);
        if (lblEl) return lblEl.innerText.trim();
      }
      if (el.placeholder) return el.placeholder;
      const prev = el.previousElementSibling;
      if (prev) return prev.innerText?.trim() || "";
      return "";
    };

    const navButtonTexts = ["new chat", "collapse sidebar", "expand sidebar", "conversation options", "copy", "share", "send", "attach file", "upload"];
    const mainTextarea = main.querySelector("textarea");

    const inputEls = main.querySelectorAll('input:not([type="radio"]):not([type="checkbox"]):not([type="file"]):not([type="hidden"])');
    inputEls.forEach(el => {
      formElements.push({ type: "input", label: getLabelFor(el), selector: getSelectorFor(el), value: el.value || undefined, placeholder: el.placeholder || undefined });
    });

    const selectEls = main.querySelectorAll("select");
    selectEls.forEach(el => {
      const opts = Array.from(el.options).map(o => o.text.trim()).filter(Boolean);
      formElements.push({ type: "select", label: getLabelFor(el), selector: getSelectorFor(el), value: el.options[el.selectedIndex]?.text.trim() || el.value || undefined, options: opts.length > 0 ? opts : undefined });
    });

    const radioEls = main.querySelectorAll('input[type="radio"]');
    const radioGroups = new Map();
    radioEls.forEach(el => {
      const groupKey = el.name || el.id || getSelectorFor(el);
      if (!radioGroups.has(groupKey)) radioGroups.set(groupKey, []);
      radioGroups.get(groupKey).push(el);
    });
    radioGroups.forEach((radios, groupName) => {
      const checkedRadio = radios.find(r => r.checked);
      const opts = radios.map(r => getLabelFor(r) || r.value).filter(Boolean);
      const groupSelector = groupName.startsWith("#") || groupName.includes("[") ? groupName : 'input[type="radio"][name="' + groupName + '"]';
      formElements.push({ type: "radio", label: groupName, selector: groupSelector, value: checkedRadio ? (getLabelFor(checkedRadio) || checkedRadio.value) : undefined, options: opts.length > 0 ? opts : undefined, checked: !!checkedRadio });
    });

    const checkboxEls = main.querySelectorAll('input[type="checkbox"]');
    checkboxEls.forEach(el => {
      formElements.push({ type: "checkbox", label: getLabelFor(el), selector: getSelectorFor(el), checked: el.checked, value: el.value || undefined });
    });

    const textareaEls = main.querySelectorAll("textarea");
    textareaEls.forEach(el => {
      if (el === mainTextarea) return;
      if (/ask anything|reply/i.test(el.placeholder || "")) return;
      formElements.push({ type: "textarea", label: getLabelFor(el), selector: getSelectorFor(el), value: el.value || undefined, placeholder: el.placeholder || undefined });
    });

    const formButtonEls = main.querySelectorAll("button");
    formButtonEls.forEach(el => {
      const text = el.textContent?.trim() || "";
      const textLower = text.toLowerCase();
      if (!text || text.length === 0 || text.length > 100) return;
      if (navButtonTexts.some(nav => textLower.includes(nav))) return;
      const isFormButton = /submit|confirm|apply|generate|create|start|run|save|ok|yes|no|cancel|clear|reset|search|analyze|proceed|continue/i.test(text) || el.type === "submit";
      if (!isFormButton) return;
      let btnSelector = getSelectorFor(el);
      if (!el.id && !el.getAttribute("name")) {
        btnSelector = 'button:has-text("' + text.replace(/"/g, '\\\\"') + '")';
      }
      formElements.push({ type: "button", label: text, selector: btnSelector });
    });

    return {
      text: responseText,
      artifacts,
      target_status_labels: uniqueLabels,
      errors,
      interactive_elements: [...new Set(interactiveElements)],
      form_elements: formElements,
    };
}"""


async def capture_ui_state(page: Page, config: RetryConfig | None = None) -> UIState:
    """Evaluate JS to capture UI state. Retries on transient JS errors."""
    if config is None:
        config = RetryConfig()

    @action_retry(config)
    async def _capture() -> UIState:
        logger.debug("[ui_capture] Evaluating UI state extraction JS...")
        raw = await page.evaluate(_CAPTURE_UI_STATE_JS)
        state = UIState.model_validate(raw)
        logger.debug(
            "[ui_capture] Captured: text=%d chars, artifacts=%d, forms=%d, errors=%d, labels=%d",
            len(state.text),
            len(state.artifacts) if state.artifacts else 0,
            len(state.form_elements) if state.form_elements else 0,
            len(state.errors) if state.errors else 0,
            len(state.target_status_labels) if state.target_status_labels else 0,
        )
        return state

    return await _capture()


async def capture_artifacts_panel(page: Page) -> list[Artifact]:
    """Open More/panel buttons and scan for downloadable artifacts."""
    logger.debug("[artifacts_panel] Scanning for artifacts...")

    # Strategy 1: Click "More" buttons on inline artifact widgets
    more_buttons = page.locator('button:has-text("More"), button[aria-label*="more" i]')
    more_count = await more_buttons.count()
    if more_count > 0:
        logger.debug(
            "[artifacts_panel] Found %d 'More' button(s) — clicking first visible...",
            more_count,
        )
    for i in range(more_count):
        try:
            btn = more_buttons.nth(i)
            if await btn.is_visible(timeout=1000):
                await btn.click()
                logger.debug("[artifacts_panel] Clicked 'More' button #%d", i + 1)
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    # Strategy 2: Try to open the artifacts sidebar via header icons
    sidebar_triggers = [
        page.locator('button[aria-label*="artifact" i]').first,
        page.locator('button[aria-label*="panel" i]').first,
        page.locator('button[aria-label*="file" i]').first,
        page.locator('header button, [class*="header"] button').last,
    ]
    for trigger in sidebar_triggers:
        try:
            if await trigger.is_visible(timeout=1000):
                await trigger.click()
                logger.debug("[artifacts_panel] Opened sidebar via header icon")
                await page.wait_for_timeout(1500)
                break
        except Exception:
            continue

    # Scan full page for download links
    raw_artifacts = await page.evaluate("""() => {
        const found = [];
        const body = document.body;
        const downloadLinks = body.querySelectorAll('a[download], a[href*=".csv"], a[href*=".xlsx"], a[href*=".pdf"], a[href*=".pptx"], a[href*=".png"], a[href*=".json"], a[href*=".py"], a[href*=".html"], a[href*=".zip"]');
        downloadLinks.forEach(link => {
          const name = link.download || link.textContent?.trim() || link.href?.split("/").pop()?.split("?")[0] || "file";
          if (name && name.length < 200 && !found.some(f => f.name === name)) {
            found.push({ name, type: "download", url: link.href || undefined });
          }
        });
        const blobLinks = body.querySelectorAll('a[href^="blob:"]');
        blobLinks.forEach(link => {
          const name = link.download || link.textContent?.trim() || "blob-file";
          if (!found.some(f => f.name === name)) {
            found.push({ name, type: "download", url: link.href });
          }
        });
        const allClickables = body.querySelectorAll('button, [role="menuitem"], [class*="menu"] a, [class*="dropdown"] a');
        allClickables.forEach(el => {
          const text = el.textContent?.trim() || "";
          if (/download/i.test(text) && text.length < 60) {
            if (!found.some(f => f.name === text)) {
              found.push({ name: text, type: "download" });
            }
          }
        });
        return found;
    }""")

    # Close any open menu
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)

    artifacts = [Artifact.model_validate(a) for a in raw_artifacts]
    if artifacts:
        logger.info(
            "[artifacts_panel] Found %d artifact(s): %s",
            len(artifacts),
            ", ".join(a.name for a in artifacts[:5]),
        )
    else:
        logger.debug("[artifacts_panel] No artifacts found")
    return artifacts


async def capture_inline_charts(page: Page, output_dir: Path) -> list[dict]:
    """Screenshot inline chart/SVG/canvas elements as PNG files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    chart_index = 0

    locator_specs = [
        '[class*="chart"], [class*="visualization"], [class*="plot"], [class*="recharts"], [class*="vega"]',
        'svg:has(rect):has(text), svg:has(path):has(g[class*="axis"])',
        "canvas",
    ]

    for spec in locator_specs:
        elements = page.locator(spec)
        count = await elements.count()
        for i in range(count):
            try:
                el = elements.nth(i)
                if await el.is_visible(timeout=1000):
                    box = await el.bounding_box()
                    if box and box["width"] > 100 and box["height"] > 50:
                        chart_index += 1
                        filename = f"chart-{chart_index}.png"
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
