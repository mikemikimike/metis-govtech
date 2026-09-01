"""Playwright interaction protocol — structured primitives for browser actions.

Every Playwright interaction flows through one of these primitives:
- do_action(): execute an action with stated intent and optional verification
- expect(): wait for a named condition to become true
- stabilize(): explicit delay when no observable signal exists
- guard_element(): pre-check that an element is visible and enabled before acting
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from metis.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.sync_api import Page

logger = get_logger()

_PAGE_CONTEXT_JS = """() => {
    const els = [];
    document.querySelectorAll('button, input, select, textarea, a[href]').forEach(el => {
        if (!el.offsetParent && el.tagName !== 'INPUT') return;
        const tag = el.tagName.toLowerCase();
        const label = (el.textContent || '').trim().slice(0, 50)
            || el.getAttribute('aria-label')
            || el.getAttribute('placeholder')
            || el.getAttribute('name')
            || '';
        if (label) els.push(tag + ": '" + label.replace(/\\n/g, ' ') + "'");
    });
    const errors = [];
    document.querySelectorAll('[role="alert"]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t && t.length > 0 && t.length < 200) errors.push(t);
    });
    const buttons = Array.from(document.querySelectorAll('button'));
    const hasSpinner = buttons.some(b => (b.textContent || '').includes('Stop generating'));
    const hasDialog = !!document.querySelector('[role="dialog"]');
    return {
        url: location.href,
        els: els.slice(0, 30),
        errors: errors.slice(0, 5),
        hasSpinner: hasSpinner,
        hasDialog: hasDialog
    };
}"""


@dataclass
class PageContext:
    """Snapshot of page state captured on the failure path."""

    url: str = ""
    visible_elements: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    has_spinner: bool = False
    has_dialog: bool = False


@dataclass
class ActionResult:
    """Outcome of a structured browser action."""

    intent: str
    succeeded: bool
    duration_ms: float
    effect_verified: bool = True
    error: str | None = None
    page_context: PageContext | None = None


@dataclass
class Expectation:
    """Outcome of waiting for a named condition."""

    description: str
    satisfied: bool
    waited_ms: float
    timeout_ms: float
    page_context: PageContext | None = None


def _capture_page_context(page: Page) -> PageContext:
    """Snapshot interactive elements on the failure path. Never raises."""
    try:
        raw = page.evaluate(_PAGE_CONTEXT_JS)
        return PageContext(
            url=raw.get("url", ""),
            visible_elements=raw.get("els", []),
            error_messages=raw.get("errors", []),
            has_spinner=raw.get("hasSpinner", False),
            has_dialog=raw.get("hasDialog", False),
        )
    except Exception:
        return PageContext(url="(page unreachable)")


def _log_page_context(prefix: str, ctx: PageContext) -> None:
    """Emit structured page context to the logger."""
    logger.warning("%s  Page context: url=%s", prefix, ctx.url)
    if ctx.visible_elements:
        logger.warning("%s  Visible: %s", prefix, ", ".join(ctx.visible_elements[:15]))
    else:
        logger.warning("%s  Visible: (none)", prefix)
    if ctx.error_messages:
        logger.warning("%s  Errors: %s", prefix, "; ".join(ctx.error_messages))
    logger.warning(
        "%s  State: spinner=%s, dialog=%s", prefix, ctx.has_spinner, ctx.has_dialog
    )


def do_action(
    page: Page,
    intent: str,
    act: Callable[[], Any],
    verify: str | None = None,
    verify_args: Any = None,
    verify_timeout_ms: int = 3000,
) -> ActionResult:
    """Execute a Playwright action with intent declaration and effect verification.

    - intent: human-readable description of what this action does
    - act: callable that performs the Playwright interaction (one atomic call)
    - verify: optional JS predicate (returns true when effect is confirmed)
    - verify_args: argument passed to the JS predicate function
    - verify_timeout_ms: max time to wait for verify predicate

    Never raises. Returns ActionResult with succeeded=False on failure.
    """
    logger.info("[action] Intent: %r", intent)
    start = time.time()

    try:
        act()
    except Exception as exc:
        duration_ms = (time.time() - start) * 1000
        error_str = f"{type(exc).__name__}: {exc}"
        ctx = _capture_page_context(page)
        if ctx.has_spinner:
            error_str += " (spinner/loading indicator present — page still processing)"
        if ctx.has_dialog:
            error_str += " (dialog/modal is blocking the page)"
        logger.warning("[action] Failed: %r — %s", intent, error_str)
        _log_page_context("[action]", ctx)
        return ActionResult(
            intent=intent,
            succeeded=False,
            duration_ms=duration_ms,
            effect_verified=False,
            error=error_str,
            page_context=ctx,
        )

    if verify is None:
        duration_ms = (time.time() - start) * 1000
        logger.info("[action] Completed: %r in %.0fms", intent, duration_ms)
        return ActionResult(intent=intent, succeeded=True, duration_ms=duration_ms)

    # Wait for effect using Playwright's native polling
    try:
        if verify_args is not None:
            page.wait_for_function(verify, arg=verify_args, timeout=verify_timeout_ms)
        else:
            page.wait_for_function(verify, timeout=verify_timeout_ms)
        duration_ms = (time.time() - start) * 1000
        logger.info("[action] Completed: %r in %.0fms (verified)", intent, duration_ms)
        return ActionResult(
            intent=intent,
            succeeded=True,
            duration_ms=duration_ms,
            effect_verified=True,
        )
    except Exception:
        duration_ms = (time.time() - start) * 1000
        logger.warning(
            "[action] Completed: %r in %.0fms (effect NOT verified)",
            intent,
            duration_ms,
        )
        ctx = _capture_page_context(page)
        _log_page_context("[action]", ctx)
        return ActionResult(
            intent=intent,
            succeeded=True,
            duration_ms=duration_ms,
            effect_verified=False,
            page_context=ctx,
        )


def expect(
    page: Page,
    description: str,
    predicate: str,
    args: Any = None,
    timeout_ms: int = 5000,
    poll_ms: int = 200,
) -> Expectation:
    """Wait for a named condition. Returns structured result, never raises.

    - description: what we're waiting for (appears in logs)
    - predicate: JS expression returning bool
    - args: argument passed to the JS function
    - timeout_ms: maximum wait (ceiling, not duration)
    - poll_ms: polling interval (passed to Playwright's wait_for_function)
    """
    logger.info("[expect] Waiting: %r (timeout=%dms)", description, timeout_ms)
    start = time.time()

    try:
        if args is not None:
            page.wait_for_function(
                predicate, arg=args, polling=poll_ms, timeout=timeout_ms
            )
        else:
            page.wait_for_function(predicate, polling=poll_ms, timeout=timeout_ms)
        waited_ms = (time.time() - start) * 1000
        logger.info("[expect] Satisfied: %r in %.0fms", description, waited_ms)
        return Expectation(
            description=description,
            satisfied=True,
            waited_ms=waited_ms,
            timeout_ms=timeout_ms,
        )
    except Exception:
        waited_ms = (time.time() - start) * 1000
        logger.warning(
            "[expect] NOT satisfied: %r after %.0fms", description, waited_ms
        )
        ctx = _capture_page_context(page)
        _log_page_context("[expect]", ctx)
        return Expectation(
            description=description,
            satisfied=False,
            waited_ms=waited_ms,
            timeout_ms=timeout_ms,
            page_context=ctx,
        )


def stabilize(page: Page, description: str, ms: int = 500) -> None:
    """Explicit stabilization delay when no observable signal exists.

    Use only when there is genuinely no DOM signal to wait for
    (e.g., React re-render after state update, CSS animation settling).
    """
    logger.debug("[stabilize] %s (%dms)", description, ms)
    page.wait_for_timeout(ms)


def is_page_active(page: Page) -> bool:
    """Check if the target is still generating a response.

    Detection signals (ordered by reliability in Orca):
    1. "Stop generating" button — standard LLM chat indicator
    2. aria-busy="true" on <main> (Orca's chat container)
    3. progressbar role visible
    4. status role with activity text (Orca agent status labels)
    5. CSS spinner classes (near-universal across frameworks)
    """
    # Check 1: "Stop generating" button visible
    try:
        stop_btn = page.get_by_role("button", name="Stop generating")
        if stop_btn.count() > 0 and stop_btn.first.is_visible(timeout=100):
            return True
    except Exception:
        pass

    # Check 2: textarea placeholder says "Generating response..."
    try:
        textarea = page.locator("textarea").first
        placeholder = textarea.get_attribute("placeholder") or ""
        if "Generating" in placeholder:
            return True
    except Exception:
        pass

    return False


def wait_until_settled(
    page: Page,
    *,
    poll_ms: int = 3000,
    idle_timeout_ms: int = 30000,
    hard_ceiling_ms: int = 600000,
) -> Expectation:
    """Wait until the page stops showing activity indicators.

    Keeps waiting as long as is_page_active() returns True.
    Only stops when:
    - Activity indicators have been absent for idle_timeout_ms, OR
    - hard_ceiling_ms total elapsed (absolute safety cap)

    Returns Expectation with satisfied=True if settled, False if hit ceiling.
    """
    logger.info(
        "[wait_settled] Waiting for page to settle (idle=%dms, ceiling=%dms)",
        idle_timeout_ms,
        hard_ceiling_ms,
    )
    start = time.time()

    while True:
        elapsed_ms = (time.time() - start) * 1000
        if elapsed_ms >= hard_ceiling_ms:
            logger.warning("[wait_settled] Hard ceiling reached (%.0fms)", elapsed_ms)
            ctx = _capture_page_context(page)
            return Expectation(
                description="wait_until_settled",
                satisfied=False,
                waited_ms=elapsed_ms,
                timeout_ms=hard_ceiling_ms,
                page_context=ctx,
            )

        if is_page_active(page):
            try:
                page.wait_for_timeout(poll_ms)
            except Exception:
                elapsed_ms = (time.time() - start) * 1000
                logger.warning("[wait_settled] Page context lost (%.0fms)", elapsed_ms)
                return Expectation(
                    description="wait_until_settled",
                    satisfied=False,
                    waited_ms=elapsed_ms,
                    timeout_ms=hard_ceiling_ms,
                )
            continue

        # No activity — wait idle_timeout_ms to confirm it's truly done
        idle_start = time.time()
        settled = True
        while (time.time() - idle_start) * 1000 < idle_timeout_ms:
            remaining_ceiling = hard_ceiling_ms - (time.time() - start) * 1000
            if remaining_ceiling <= 0:
                break
            try:
                page.wait_for_timeout(min(poll_ms, int(remaining_ceiling)))
            except Exception:
                elapsed_ms = (time.time() - start) * 1000
                logger.warning("[wait_settled] Page context lost (%.0fms)", elapsed_ms)
                return Expectation(
                    description="wait_until_settled",
                    satisfied=False,
                    waited_ms=elapsed_ms,
                    timeout_ms=hard_ceiling_ms,
                )
            if is_page_active(page):
                settled = False
                break

        if not settled:
            continue

        elapsed_ms = (time.time() - start) * 1000
        logger.info("[wait_settled] Settled after %.0fms", elapsed_ms)
        return Expectation(
            description="wait_until_settled",
            satisfied=True,
            waited_ms=elapsed_ms,
            timeout_ms=hard_ceiling_ms,
        )


class GuardFailed(Exception):
    """Element did not meet preconditions (not visible, disabled, etc.)."""

    def __init__(
        self, action: str, reason: str, page_context: PageContext | None = None
    ) -> None:
        self.action = action
        self.reason = reason
        self.page_context = page_context
        super().__init__(f"Guard failed for {action!r}: {reason}")


def guard_element(
    page: Page,
    selector: str,
    *,
    action: str = "",
    timeout_ms: int = 5000,
    wait_enabled_ms: int = 10000,
) -> None:
    """Assert an element is visible and enabled before acting on it.

    If the element is visible but disabled, polls for up to *wait_enabled_ms*
    for it to become enabled (Orca temporarily disables form elements during
    processing). Raises GuardFailed with page context if the element isn't ready.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=timeout_ms)

        # Wait for element to become enabled (handles temporary disable during processing)
        deadline = time.time() + wait_enabled_ms / 1000
        while not locator.is_enabled(timeout=500):
            if time.time() >= deadline:
                ctx = _capture_page_context(page)
                raise GuardFailed(
                    action or selector, f"element {selector!r} is disabled", ctx
                )
            page.wait_for_timeout(500)

        aria_disabled = locator.get_attribute("aria-disabled")
        if aria_disabled == "true":
            # Also wait for aria-disabled to clear
            while aria_disabled == "true" and time.time() < deadline:
                page.wait_for_timeout(500)
                aria_disabled = locator.get_attribute("aria-disabled")
            if aria_disabled == "true":
                ctx = _capture_page_context(page)
                raise GuardFailed(
                    action or selector,
                    f"element {selector!r} is aria-disabled",
                    ctx,
                )
    except GuardFailed:
        raise
    except PlaywrightTimeout:
        ctx = _capture_page_context(page)
        raise GuardFailed(
            action or selector,
            f"element {selector!r} not visible within {timeout_ms}ms",
            ctx,
        ) from None
    except Exception as exc:
        ctx = _capture_page_context(page)
        raise GuardFailed(
            action or selector, f"locator check failed: {exc}", ctx
        ) from None
