"""OrcaPlaywright-based runner — drives simulations against browser targets."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from metis.core.logging import get_logger

from ...runner import Runner
from ...types import (
    ActionSlot,
    Artifact,
    ChosenAction,
    FormElement,
    Observation,
    RunConfig,
    UIState,
)
from ._auth import login
from ._page_actions import auto_fill_and_submit, send_message, upload_file
from ._recovery import _recover_page
from ._ui_capture import (
    capture_artifacts_panel,
    capture_inline_charts,
    capture_ui_state,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

    from ._config import OrcaPlaywrightRunnerConfig

logger = get_logger()


def _value_text(value: str | list[str] | int | float | None) -> str | None:
    """Convert the widened ChosenAction.value to a plain string for DOM calls."""
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def _ui_state_to_observation(ui_state: UIState) -> Observation:
    """Convert internal UIState to the transport-agnostic Observation."""
    available_actions: list[ActionSlot] = []
    for el in ui_state.form_elements:
        available_actions.append(_form_element_to_action_slot(el))
    return Observation(
        text=ui_state.text,
        artifacts=ui_state.artifacts,
        errors=ui_state.errors,
        available_actions=available_actions,
        status_labels=ui_state.target_status_labels,
    )


def _form_element_to_action_slot(el: FormElement) -> ActionSlot:
    """Convert a FormElement to an ActionSlot."""
    return ActionSlot(
        id=el.selector,
        kind=el.type,
        label=el.label,
        options=el.options,
    )


class OrcaPlaywrightRunner(Runner):
    """Runner implementation using Playwright to interact with a browser target.

    Note: selectors, auth flow, and page interactions are hardcoded for the
    Orca chat UI. Adapting to other browser targets requires subclassing or
    a new runner.
    """

    def __init__(
        self,
        page: Page,
        config: OrcaPlaywrightRunnerConfig,
        fixtures_dir: Path,
        run_dir: Path,
    ) -> None:
        self._page = page
        self._config = config
        self._fixtures_dir = fixtures_dir
        self._run_dir = run_dir
        self._uploaded_files: set[str] = set()

    async def setup(self, config: RunConfig) -> None:
        """Authenticate and prepare the browser session."""
        logger.info("[playwright-runner] Setup: logging in...")
        await login(self._page, self._config)

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Execute chosen actions, send message, capture and return observation."""
        page = self._page
        config = self._config

        has_new_file_upload = False
        has_form_submit = False

        # Execute actions before sending the message
        if actions:
            logger.info("[playwright-runner] Executing %d action(s)...", len(actions))
        for action_idx, action in enumerate(actions, 1):
            value = _value_text(action.value)
            kind = self._infer_action_kind(action)

            if kind == "file_upload":
                if value and value in self._uploaded_files:
                    logger.info(
                        "[playwright-runner]   Action %d: SKIP duplicate upload '%s'",
                        action_idx,
                        value,
                    )
                    continue
                file_name = value or action.id
                file_path = self._fixtures_dir / file_name
                if not file_path.exists():
                    logger.warning(
                        "[playwright-runner]   Action %d: SKIP upload '%s' — file not found",
                        action_idx,
                        file_name,
                    )
                    continue
                logger.info(
                    "[playwright-runner]   Action %d: FILE_UPLOAD '%s'",
                    action_idx,
                    file_name,
                )
                await upload_file(page, file_path)
                self._uploaded_files.add(file_name)
                has_new_file_upload = True

            elif kind == "button":
                logger.info(
                    "[playwright-runner]   Action %d: BUTTON_CLICK '%s'",
                    action_idx,
                    action.id,
                )
                try:
                    is_css = bool(re.search(r"[.#\[\]=:>~+]", action.id))
                    if is_css:
                        await page.locator(action.id).first.click(timeout=5000)
                    else:
                        await page.get_by_text(action.id, exact=True).first.click(
                            timeout=5000
                        )
                    await page.wait_for_timeout(1000)
                except Exception as exc:
                    logger.warning(
                        "[playwright-runner]   Action %d: Click FAILED: %s",
                        action_idx,
                        exc,
                    )
                if re.search(
                    r"submit|generate|run|start|create|analyze|confirm",
                    action.id,
                    re.IGNORECASE,
                ):
                    has_form_submit = True

            elif kind in ("select", "input", "textarea", "radio", "checkbox"):
                fill_value = value or ""
                logger.info(
                    "[playwright-runner]   Action %d: FORM_FILL '%s' = %r",
                    action_idx,
                    action.id,
                    fill_value,
                )
                try:
                    el = page.locator(action.id).first
                    tag_name = await el.evaluate("e => e.tagName.toLowerCase()")
                    if tag_name == "select":
                        try:
                            await el.select_option(label=fill_value)
                        except Exception:
                            await el.select_option(fill_value)
                    elif tag_name == "input":
                        input_type = await el.evaluate("e => e.type")
                        if input_type in ("radio", "checkbox"):
                            await el.check()
                        else:
                            await el.fill(fill_value)
                    elif tag_name == "textarea":
                        await el.fill(fill_value)
                    else:
                        await el.click()
                    await page.wait_for_timeout(500)
                except Exception as exc:
                    logger.warning(
                        "[playwright-runner]   Action %d: FORM_FILL FAILED: %s",
                        action_idx,
                        exc,
                    )

        # Auto-fill if no form submit detected
        if not has_form_submit:
            form_submitted = await auto_fill_and_submit(page)
            if form_submitted:
                has_form_submit = True

        # Determine response timeout
        response_timeout: int | None = None
        if has_new_file_upload or has_form_submit:
            response_timeout = max(config.timeouts.response_wait_ms, 180000)

        # Send message or wait for form processing
        if has_form_submit:
            logger.info(
                "[playwright-runner] Form submitted — waiting for processing..."
            )
            processing_deadline = time.time() * 1000 + (
                response_timeout or config.timeouts.response_wait_ms
            )
            await page.wait_for_timeout(5000)
            poll_count = 0
            while time.time() * 1000 < processing_deadline:
                still_processing = await page.evaluate("""() => {
                    const hasSpinner = document.querySelector('[class*="loading"], [class*="spinner"], [class*="animate-spin"]') !== null;
                    const hasTyping = document.querySelector('[class*="typing"], [class*="streaming"]') !== null;
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const hasStop = buttons.some(b => b.textContent?.includes('Stop generating'));
                    return hasSpinner || hasTyping || hasStop;
                }""")
                if not still_processing:
                    break
                poll_count += 1
                if poll_count % 5 == 1:
                    logger.info(
                        "[playwright-runner] Still processing (poll #%d)...",
                        poll_count,
                    )
                await page.wait_for_timeout(3000)
            await page.wait_for_timeout(2000)
            ui_state = await capture_ui_state(page)
        else:
            logger.info("[playwright-runner] Sending message to target...")
            ui_state = await send_message(
                page, message, config, timeout_override=response_timeout
            )

        # Check artifacts panel if response hints at downloads
        if not ui_state.artifacts:
            response_hint = bool(
                re.search(
                    r"download|generated|ready|report|results|complete|export|file|artifact|chart|plot",
                    ui_state.text,
                    re.IGNORECASE,
                )
            )
            if response_hint or has_new_file_upload or has_form_submit:
                panel_artifacts = await capture_artifacts_panel(page)
                if panel_artifacts:
                    ui_state.artifacts = panel_artifacts

        # Download artifacts
        if ui_state.artifacts:
            await self._download_artifacts(ui_state.artifacts)

        # Capture inline charts
        try:
            chart_dir = self._run_dir / "artifacts" / "charts"
            await capture_inline_charts(page, chart_dir)
        except Exception:
            pass

        return _ui_state_to_observation(ui_state)

    async def teardown(self) -> None:
        """Close the browser context."""
        await self._page.context.close()

    async def get_session_id(self) -> str | None:
        """Extract session ID from the page URL."""
        try:
            chat_url = self._page.url
            match = re.search(r"/chat/(sess-[a-z0-9-]+)", chat_url, re.IGNORECASE)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    async def recover(self) -> None:
        """Lightweight page recovery: refresh + wait for chat textarea."""
        await _recover_page(self._page, self._config)

    def _infer_action_kind(self, action: ChosenAction) -> str:
        """Infer the DOM operation type from an action's id."""
        aid = action.id.lower()
        if "file" in aid and "upload" in aid:
            return "file_upload"
        if action.value is None and re.search(r"button|btn|submit", aid):
            return "button"
        # If the action has a value, it's likely a form fill
        if action.value is not None:
            return "input"
        return "button"

    async def _download_artifacts(self, artifacts: list[Artifact]) -> None:
        """Download detected artifacts to disk."""
        page = self._page
        artifacts_dir = self._run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        for artifact in artifacts:
            if artifact.type != "download":
                continue
            try:
                url = artifact.url
                name = artifact.name
                if url:
                    escaped_url = url.replace("\\", "\\\\").replace('"', '\\"')
                    escaped_name = name.replace("\\", "\\\\").replace('"', '\\"')
                    link = page.locator(
                        f'a[href="{escaped_url}"], a[download="{escaped_name}"]'
                    ).first
                    try:
                        link_exists = await link.is_visible(timeout=1000)
                    except Exception:
                        link_exists = False

                    if link_exists:
                        async with page.expect_download(timeout=15000) as download_info:
                            await link.click()
                        download = await download_info.value
                        filename = Path(download.suggested_filename or name).name
                        dest_path = artifacts_dir / filename
                        await download.save_as(str(dest_path))
                    elif url.startswith(("http", "blob:")):
                        async with page.expect_download(timeout=15000) as download_info:
                            await page.evaluate(
                                """(url) => {
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = '';
                                    document.body.appendChild(a);
                                    a.click();
                                    a.remove();
                                }""",
                                url,
                            )
                        download = await download_info.value
                        filename = Path(download.suggested_filename or name).name
                        dest_path = artifacts_dir / filename
                        await download.save_as(str(dest_path))
            except Exception as exc:
                logger.warning(
                    "[playwright-runner] Download failed for '%s': %s",
                    artifact.name,
                    exc,
                )


from ._factory import OrcaPlaywrightRunnerFactory  # noqa: E402

__all__ = ["OrcaPlaywrightRunner", "OrcaPlaywrightRunnerFactory"]
