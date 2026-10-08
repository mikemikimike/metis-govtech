"""OrcaPlaywright-based runner — drives simulations against browser targets."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from metis.core.logging import get_logger

from ...exceptions import SimulationError
from ...runner import Runner
from ...types import (
    ActionResult,
    ActionSlot,
    Artifact,
    ButtonClickAction,
    ChosenAction,
    FormElement,
    FormFillAction,
    Observation,
    RunConfig,
    UIState,
    UploadFileAction,
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


def _ui_state_to_observation(
    ui_state: UIState, action_results: list[ActionResult]
) -> Observation:
    """Convert internal UIState to the transport-agnostic Observation.

    ``ui_state.errors`` is error text scraped from the page, which no submitted
    action accounts for, so it becomes a turn-level notice. ``available_actions``
    stays a list — possibly empty — because the capture really did look.
    ``delivered`` is always ``True`` (I5): this runner has no seam that
    declines a turn before sending it.
    """
    available_actions: list[ActionSlot] = []
    for el in ui_state.form_elements:
        available_actions.append(_form_element_to_action_slot(el))
    return Observation(
        text=ui_state.text,
        artifacts=ui_state.artifacts,
        response_notices=ui_state.errors,
        action_results=action_results,
        available_actions=available_actions,
        status_labels=ui_state.target_status_labels,
        delivered=True,
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

    Upload staging is not this runner's concern: the orchestrator withholds an
    upload naming a fixture the scenario never staged, so ``send_turn`` is
    handed only actions worth attempting. The residual ``_fixture_path`` check
    in the action loop is a re-read at dispatch time, not that gate.
    """

    def __init__(
        self,
        page: Page,
        config: OrcaPlaywrightRunnerConfig,
        fixtures_dir: Path,
        run_dir: Path,
        experiment_root: Path,
    ) -> None:
        self._page = page
        self._config = config
        self._fixtures_dir = fixtures_dir
        self._run_dir = run_dir
        self._experiment_root = experiment_root
        self._uploaded_files: set[str] = set()
        self._page_dirty = False

    async def setup(self, config: RunConfig) -> None:
        """Apply this run's response wait and prepare the browser session."""
        # Each runner owns its timeout settings, including during concurrent runs.
        self._config = self._config.model_copy(
            update={
                "timeouts": self._config.timeouts.model_copy(
                    update={"response_wait_ms": config.response_wait_ms}
                )
            }
        )
        logger.info("[playwright-runner] Setup: logging in...")
        await login(self._page, self._config)

    def _fixture_path(self, name: str) -> Path | None:
        """``fixtures_dir/name`` if it is a file inside the fixtures directory."""
        root = self._fixtures_dir.resolve()
        path = (self._fixtures_dir / name).resolve()
        if path == root or not path.is_relative_to(root) or not path.is_file():
            return None
        return path

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Deliver a turn, reloading first if a prior turn left the DOM dirty.

        I3: a prior turn left the DOM in an unknown state. Reload before
        touching it here, on the *next* turn, rather than on the failing
        turn's way out — so the cost is only paid when there actually is a
        next turn. #361.

        The reload itself is best-effort: if it fails, the page stays
        marked dirty so the turn after this one tries again, rather than
        letting a reload failure crash the run.
        """
        if self._page_dirty:
            try:
                await _recover_page(self._page, self._config)
            except Exception as exc:
                logger.warning(
                    "[playwright-runner] Page recovery failed, will retry"
                    " next turn: %s",
                    exc,
                )
            else:
                self._page_dirty = False
        try:
            return await self._send_turn(message, actions)
        except SimulationError:
            self._page_dirty = True
            raise

    async def _send_turn(
        self, message: str, actions: list[ChosenAction]
    ) -> Observation:
        """Execute chosen actions, send message, capture and return observation."""
        page = self._page
        config = self._config

        # One row per received action (I1). Optimistic: each seam below that
        # drops an action flips its own row, so a row left untouched really was
        # delivered. Local rather than instance state — this runner is not being
        # refactored, and send_turn is the only writer.
        action_results = [
            ActionResult(action_index=index, succeeded=True)
            for index in range(len(actions))
        ]

        def fail(index: int, detail: str, *, retryable: bool | None = None) -> None:
            # A fresh row, not model_copy(update=...): model_copy skips
            # validation, so it would happily produce succeeded=False with an
            # empty detail, which the model otherwise forbids.
            action_results[index] = ActionResult(
                action_index=index,
                succeeded=False,
                detail=detail,
                retryable=retryable,
            )

        has_new_file_upload = False
        has_form_submit = False

        # Execute actions before sending the message
        if actions:
            logger.info("[playwright-runner] Executing %d action(s)...", len(actions))
        for action_idx, action in enumerate(actions, 1):
            index = action_idx - 1  # action_idx is 1-based for the log lines
            match action:
                case UploadFileAction(filename=filename):
                    if filename in self._uploaded_files:
                        logger.info(
                            "[playwright-runner]   Action %d: SKIP duplicate upload '%s'",
                            action_idx,
                            filename,
                        )
                        fail(
                            index,
                            f"Not submitted: file '{filename}' is already attached"
                            " to this conversation",
                            retryable=False,
                        )
                        continue
                    # The orchestrator already confirmed this fixture was staged;
                    # this is a re-read at dispatch time, so it can still fail if
                    # the file went away mid-run.
                    file_path = self._fixture_path(filename)
                    if file_path is None:
                        fail(
                            index,
                            f"Not submitted: file '{filename}' was no longer"
                            " readable under the fixtures directory",
                            retryable=False,
                        )
                        continue
                    logger.info(
                        "[playwright-runner]   Action %d: FILE_UPLOAD '%s'",
                        action_idx,
                        filename,
                    )
                    await upload_file(page, file_path)
                    self._uploaded_files.add(filename)
                    has_new_file_upload = True

                case ButtonClickAction(slot_id=selector):
                    logger.info(
                        "[playwright-runner]   Action %d: BUTTON_CLICK '%s'",
                        action_idx,
                        selector,
                    )
                    try:
                        is_css = bool(re.search(r"[.#\[\]=:>~+]", selector))
                        if is_css:
                            await page.locator(selector).first.click(timeout=5000)
                        else:
                            await page.get_by_text(selector, exact=True).first.click(
                                timeout=5000
                            )
                        await page.wait_for_timeout(1000)
                    except Exception as exc:
                        logger.warning(
                            "[playwright-runner]   Action %d: Click FAILED: %s",
                            action_idx,
                            exc,
                        )
                        # Retryable: a click the DOM refused may well land once
                        # the page settles.
                        fail(
                            index,
                            f"Click on '{selector}' failed: {exc}",
                            retryable=True,
                        )
                    if re.search(
                        r"submit|generate|run|start|create|analyze|confirm",
                        selector,
                        re.IGNORECASE,
                    ):
                        has_form_submit = True

                case FormFillAction(slot_id=selector, value=value):
                    fill_value = _value_text(value) or ""
                    logger.info(
                        "[playwright-runner]   Action %d: FORM_FILL '%s' = %r",
                        action_idx,
                        selector,
                        fill_value,
                    )
                    try:
                        el = page.locator(selector).first
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
                        fail(
                            index,
                            f"Filling '{selector}' failed: {exc}",
                            retryable=True,
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

        return _ui_state_to_observation(ui_state, action_results)

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

    async def _download_artifacts(self, artifacts: list[Artifact]) -> None:
        """Download detected artifacts to disk."""
        page = self._page
        artifacts_dir = self._run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        for artifact in artifacts:
            # The UI capture parks the download href in `path`, but Artifact.path
            # is contracted to be a path relative to the experiment root — so it
            # is cleared here and only a completed save_as below may re-set it.
            url = artifact.path
            artifact.path = None
            name = artifact.name
            try:
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
                        artifact.path = (
                            Path(dest_path)
                            .resolve()
                            .relative_to(self._experiment_root.resolve())
                            .as_posix()
                        )
                        artifact.state = "received"
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
                        artifact.path = (
                            Path(dest_path)
                            .resolve()
                            .relative_to(self._experiment_root.resolve())
                            .as_posix()
                        )
                        artifact.state = "received"
            except Exception as exc:
                logger.warning(
                    "[playwright-runner] Download failed for '%s' (%s): %s",
                    artifact.name,
                    url or "no url",
                    exc,
                )


from ._factory import OrcaPlaywrightRunnerFactory  # noqa: E402

__all__ = ["OrcaPlaywrightRunner", "OrcaPlaywrightRunnerFactory"]
