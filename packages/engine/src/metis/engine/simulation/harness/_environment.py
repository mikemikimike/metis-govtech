"""Turn loop orchestration — drives a simulation run to completion.

Instantiates the UserAgent directly (no subprocess), sends messages through
the Playwright page, enforces stopping conditions, and assembles the final
RunRecord.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import Page

from metis.core.logging import get_logger

from ..exceptions import (
    ConsecutiveFailureEscalation,
    PostSubmissionObservationError,
    ResponseTimeoutError,
    RunRecoverableError,
    TransientDOMError,
    TurnRecoverableError,
)
from ..types import (
    ButtonClickAction,
    CollectedArtifact,
    ConversationTurn,
    FileUploadAction,
    FormFillAction,
    Persona,
    RunConfig,
    RunMeta,
    RunOutcome,
    RunRecord,
    Scenario,
    UIAction,
    UIState,
    UserAgentInput,
)
from ..user_agent.agent import UserAgent
from ._auth import dismiss_modals
from ._config import HarnessConfig
from ._page_actions import auto_fill_and_submit, send_message, upload_file
from ._ui_capture import (
    capture_artifacts_panel,
    capture_inline_charts,
    capture_ui_state,
)

if TYPE_CHECKING:
    from metis.engine.tui import SimulationState, TUIContext

logger = get_logger()


async def _recover_page(page: Page, config: HarnessConfig) -> None:
    """Lightweight page recovery: refresh + wait for chat textarea."""
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    await dismiss_modals(page)
    await page.wait_for_selector("textarea", timeout=10000)


async def _recover_and_check(
    page: Page,
    config: HarnessConfig,
    sent_message: str,
) -> UIState | None:
    """Recover page and check whether the sent message got a response.

    Returns UIState if the message was already processed (don't resend),
    or None if the message was never received (safe to resend).
    """
    await _recover_page(page, config)
    ui_state = await capture_ui_state(page)

    last_user_msg = await page.evaluate("""() => {
        const msgs = document.querySelectorAll('.message-user');
        return msgs.length ? msgs[msgs.length - 1].innerText?.trim() || "" : "";
    }""")

    if sent_message[:80] in (last_user_msg or ""):
        return ui_state
    return None


async def _wait_for_processing(page: Page, turn_count: int) -> None:
    """Wait for Orca to finish any active processing."""
    await page.wait_for_timeout(2000)
    poll_count = 0
    while poll_count < 60:
        still_processing = await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button'));
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
            logger.info(
                "[turn %d] Waiting for processing to complete (poll #%d)...",
                turn_count,
                poll_count,
            )
        await page.wait_for_timeout(2000)
    if poll_count > 0:
        logger.info(
            "[turn %d] Processing settled after %d poll(s)", turn_count, poll_count
        )


async def run_simulation(
    page: Page,
    config: HarnessConfig,
    persona: Persona,
    scenario: Scenario,
    run_dir: Path,
    fixtures_dir: Path,
    trial: int = 1,
    state: SimulationState | None = None,
    tui_ctx: TUIContext | None = None,
) -> RunRecord:
    """Run a full simulation run: drive the turn loop and produce a RunRecord.

    :param page: Playwright page already logged-in and on the chat screen.
    :param config: Harness config with timeouts and auth settings.
    :param persona: The persona driving the simulated user.
    :param scenario: The experiment scenario defining the goal.
    :param run_dir: Pre-created run folder (``runs/<scenario>-<persona>-<trial>/``).
        Artifacts are written to ``run_dir/artifacts/`` during the turn loop.
    :param fixtures_dir: Directory containing fixture files for upload.
    :param trial: 1-based trial index (used for state updates).
    :param state: Optional :class:`SimulationState` for TUI progress tracking.
    :param tui_ctx: Optional :class:`TUIContext` to refresh after state mutations.
    :returns: A complete RunRecord with conversation, outcome, and artifacts.
    """
    run_config = RunConfig(
        persona=persona.id,
        scenario=scenario.id,
        metric_refs=scenario.metric_refs,
        response_wait_ms=scenario.response_wait_ms,
    )

    start_time = time.time()
    conversation: list[ConversationTurn] = []
    artifacts_collected: list[CollectedArtifact] = []
    turn_count = 0

    logger.info("=" * 60)
    logger.info("[sim] START: %s x %s", persona.id, scenario.id)
    logger.info(
        "[sim] Config: max_turns=%d, timeout=%d min, response_wait=%dms",
        run_config.max_turns,
        run_config.timeout_minutes,
        run_config.response_wait_ms or config.timeouts.response_wait_ms,
    )
    logger.info("[sim] Scenario goal: %s", scenario.description[:120])
    logger.info("=" * 60)

    # Instantiate user agent directly (no subprocess)
    logger.info("[sim] Initializing UserAgent (persona=%s)...", persona.id)
    agent = UserAgent(persona=persona, scenario=scenario)

    # Generate opening message
    logger.info("[sim] Generating opening message via LLM...")
    opening_start = time.time()
    try:
        opening = await agent.generate_opening()
    except Exception as exc:
        logger.info("[sim] STOP: system_error (opening LLM call failed: %s)", exc)
        return _build_record(
            "system_error",
            run_config,
            [],
            [],
            start_time,
            None,
        )
    logger.info(
        "[sim] Opening message (%.1fs): %r",
        time.time() - opening_start,
        opening.message[:120],
    )
    if opening.ui_actions:
        logger.info(
            "[sim] Opening UI actions: %s",
            ", ".join(type(a).__name__ for a in opening.ui_actions),
        )

    # Dismiss modals before starting the turn loop
    logger.info("[sim] Dismissing modals before turn loop...")
    await dismiss_modals(page)

    # Track uploaded files to avoid duplicates
    uploaded_files: set[str] = set()

    # Capture target session ID from URL
    target_session_id: str | None = None

    # Initial state from opening
    current_message: str = opening.message
    current_ui_actions: list[UIAction] = opening.ui_actions
    current_decision: str = opening.decision

    consecutive_failures = 0

    # Turn loop
    while True:
        turn_count += 1
        turn_start = time.time()
        elapsed_s = time.time() - start_time

        logger.info("-" * 50)
        logger.info(
            "[turn %d] Starting (elapsed: %.1fs / %ds max)",
            turn_count,
            elapsed_s,
            run_config.timeout_minutes * 60,
        )

        # Notify TUI of turn progress
        if state:
            state.update_run_turn(
                scenario.id,
                persona.id,
                trial=trial,
                turn=turn_count,
                max_turns=run_config.max_turns,
                detail="sending message...",
            )
            if tui_ctx:
                tui_ctx.refresh()

        # --- Stopping rule 1: max turns ---
        if turn_count > run_config.max_turns:
            logger.info(
                "[turn %d] STOP: max_turns reached (%d)",
                turn_count,
                run_config.max_turns,
            )
            return _build_record(
                "max_turns",
                run_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # --- Stopping rule 2: timeout ---
        if elapsed_s >= run_config.timeout_minutes * 60:
            logger.info(
                "[turn %d] STOP: timeout (%.1fs >= %ds)",
                turn_count,
                elapsed_s,
                run_config.timeout_minutes * 60,
            )
            return _build_record(
                "timeout",
                run_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # --- Stopping rule: user abandoned ---
        if current_decision == "giving_up":
            logger.info("[turn %d] STOP: user_abandoned (agent gave up)", turn_count)
            return _build_record(
                "user_abandoned",
                run_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # --- Stopping rule: goal achieved (with artifact capture window) ---
        if current_decision == "goal_achieved":
            logger.info(
                "[turn %d] STOP: goal_achieved — entering 2-min artifact capture phase...",
                turn_count,
            )
            artifact_deadline = time.time() + 120  # 2 min
            attempt = 0
            while time.time() < artifact_deadline and not artifacts_collected:
                attempt += 1
                logger.info(
                    "[turn %d] Artifact capture attempt %d (%.0fs remaining)...",
                    turn_count,
                    attempt,
                    artifact_deadline - time.time(),
                )
                panel_artifacts = await capture_artifacts_panel(page)
                if panel_artifacts:
                    logger.info(
                        "[turn %d] Found %d artifact(s) — downloading...",
                        turn_count,
                        len(panel_artifacts),
                    )
                    downloaded = await _download_artifacts(
                        page,
                        [
                            {"name": a.name, "type": a.type, "url": a.url}
                            for a in panel_artifacts
                        ],
                        run_dir / "artifacts",
                    )
                    for dl in downloaded:
                        artifacts_collected.append(
                            CollectedArtifact(
                                filename=dl["filename"],
                                collected_at_turn=turn_count,
                                path=dl["local_path"],
                            )
                        )
                    if artifacts_collected:
                        break
                await page.wait_for_timeout(5000)

            if not artifacts_collected:
                logger.info(
                    "[turn %d] No artifacts captured after %d attempts",
                    turn_count,
                    attempt,
                )
            else:
                logger.info(
                    "[turn %d] Collected %d artifact(s)",
                    turn_count,
                    len(artifacts_collected),
                )

            return _build_record(
                "goal_achieved",
                run_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        logger.info(
            "[turn %d] Decision: %r | Message: %r",
            turn_count,
            current_decision,
            current_message[:80],
        )

        # Detect actions that trigger long processing
        has_new_file_upload = any(
            isinstance(a, FileUploadAction) and a.file not in uploaded_files
            for a in current_ui_actions
        )
        has_form_submit = any(
            isinstance(a, ButtonClickAction) for a in current_ui_actions
        )

        # Snapshot page text before actions (for stale-state detection after form submit)
        pre_submit_text = ""
        if has_form_submit:
            try:
                pre_submit_text = await page.locator("main").first.inner_text(
                    timeout=2000
                )
            except Exception:
                pass

        # Execute UI actions before sending the message
        if current_ui_actions:
            logger.info(
                "[turn %d] Executing %d UI action(s) before message...",
                turn_count,
                len(current_ui_actions),
            )
        for action_idx, action in enumerate(current_ui_actions, 1):
            if isinstance(action, FileUploadAction):
                if action.file in uploaded_files:
                    logger.info(
                        "[turn %d]   Action %d/%d: SKIP duplicate upload '%s'",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                        action.file,
                    )
                    continue
                file_path = fixtures_dir / action.file
                if not file_path.exists():
                    logger.warning(
                        "[turn %d]   Action %d/%d: SKIP upload '%s' — file not found at %s",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                        action.file,
                        file_path,
                    )
                    continue
                logger.info(
                    "[turn %d]   Action %d/%d: FILE_UPLOAD '%s'",
                    turn_count,
                    action_idx,
                    len(current_ui_actions),
                    action.file,
                )
                await upload_file(page, file_path)
                # Wait for Orca to finish processing the upload before continuing
                await _wait_for_processing(page, turn_count)
                # Only mark as uploaded if the file is visible in the UI
                file_visible = await page.evaluate(
                    """(name) => {
                        const body = document.body.innerText;
                        const baseName = name.replace(/\\.[^.]+$/, "");
                        return body.toLowerCase().includes(name.toLowerCase()) ||
                               body.toLowerCase().includes(baseName.toLowerCase());
                    }""",
                    action.file,
                )
                if file_visible:
                    uploaded_files.add(action.file)
                else:
                    logger.warning(
                        "[turn %d]   Upload of '%s' not verified — will retry next turn",
                        turn_count,
                        action.file,
                    )

            elif isinstance(action, ButtonClickAction):
                logger.info(
                    "[turn %d]   Action %d/%d: BUTTON_CLICK '%s'",
                    turn_count,
                    action_idx,
                    len(current_ui_actions),
                    action.selector,
                )
                try:
                    is_css = bool(re.search(r"[.#\[\]=:>~+]", action.selector))
                    if is_css:
                        await page.locator(action.selector).first.click(timeout=5000)
                    else:
                        await page.get_by_text(action.selector, exact=True).first.click(
                            timeout=5000
                        )
                    await page.wait_for_timeout(1000)
                    await _wait_for_processing(page, turn_count)
                    logger.info(
                        "[turn %d]   Action %d/%d: Click successful",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                    )
                except Exception as exc:
                    logger.warning(
                        "[turn %d]   Action %d/%d: Click FAILED: %s",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                        exc,
                    )

            elif isinstance(action, FormFillAction):
                fill_value = action.value

                # Override AI Model selects to "Fast (Claude Haiku)"
                try:
                    is_model_select = await page.locator(
                        action.selector
                    ).first.evaluate(
                        """el => {
                            const label = el.closest('div')?.querySelector('label')?.textContent || '';
                            return /ai model/i.test(label);
                        }"""
                    )
                except Exception:
                    is_model_select = False

                if is_model_select:
                    fill_value = "Fast (Claude Haiku)"
                    logger.info(
                        "[turn %d]   Action %d/%d: FORM_FILL (model override) '%s' = %r",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                        action.selector,
                        fill_value,
                    )
                else:
                    logger.info(
                        "[turn %d]   Action %d/%d: FORM_FILL '%s' = %r",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                        action.selector,
                        fill_value,
                    )

                try:
                    el = page.locator(action.selector).first
                    tag_name = await el.evaluate("e => e.tagName.toLowerCase()")
                    logger.debug("[turn %d]   Element tag: <%s>", turn_count, tag_name)
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
                        "[turn %d]   Action %d/%d: FORM_FILL FAILED: %s",
                        turn_count,
                        action_idx,
                        len(current_ui_actions),
                        exc,
                    )

        # Auto-fill if the user agent didn't provide form submit actions
        if not has_form_submit:
            logger.debug(
                "[turn %d] No form submit in UI actions — trying auto_fill_and_submit...",
                turn_count,
            )
            form_submitted = await auto_fill_and_submit(page)
            if form_submitted:
                has_form_submit = True

        # Determine response timeout
        response_timeout: int | None = None
        if has_new_file_upload or has_form_submit:
            response_timeout = max(config.timeouts.response_wait_ms, 180000)
            logger.info(
                "[turn %d] Extended timeout: %dms (file_upload=%s, form_submit=%s)",
                turn_count,
                response_timeout,
                has_new_file_upload,
                has_form_submit,
            )

        # Send message or wait for form processing
        send_start = time.time()
        try:
            if has_form_submit:
                logger.info(
                    "[turn %d] Form was submitted — waiting for target to process...",
                    turn_count,
                )

                processing_deadline = time.time() * 1000 + (
                    response_timeout or config.timeouts.response_wait_ms
                )
                await page.wait_for_timeout(5000)
                poll_count = 0
                while time.time() * 1000 < processing_deadline:
                    still_processing = await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const hasStop = buttons.some(b => b.textContent?.includes('Stop generating'));
                        const lastAssistant = document.querySelector('.message-assistant:last-of-type');
                        const isStreaming = lastAssistant && lastAssistant.innerText.trim() === '';
                        return hasStop || isStreaming;
                    }""")
                    if not still_processing:
                        break
                    poll_count += 1
                    if poll_count % 5 == 1:
                        logger.info(
                            "[turn %d] Still processing after form submit (poll #%d)...",
                            turn_count,
                            poll_count,
                        )
                    await page.wait_for_timeout(3000)
                logger.info(
                    "[turn %d] Form processing complete (polled %d times)",
                    turn_count,
                    poll_count,
                )
                await page.wait_for_timeout(2000)

                # Stale-state detection: if page unchanged after submit,
                # the form likely requires unfilled fields
                try:
                    post_submit_text = await page.locator("main").first.inner_text(
                        timeout=2000
                    )
                except Exception:
                    post_submit_text = ""
                if (
                    pre_submit_text
                    and post_submit_text
                    and pre_submit_text == post_submit_text
                ):
                    logger.warning(
                        "[turn %d] Page unchanged after form submit — "
                        "form may require unfilled fields",
                        turn_count,
                    )

                ui_state = await capture_ui_state(page)
            else:
                logger.info("[turn %d] Sending message to target...", turn_count)
                ui_state = await send_message(
                    page, current_message, config, timeout_override=response_timeout
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
                had_processing = has_new_file_upload or has_form_submit
                if response_hint or had_processing:
                    logger.info(
                        "[turn %d] Response hints at artifacts — checking panel...",
                        turn_count,
                    )
                    panel_artifacts = await capture_artifacts_panel(page)
                    if panel_artifacts:
                        logger.info(
                            "[turn %d] Found %d artifact(s) in panel",
                            turn_count,
                            len(panel_artifacts),
                        )
                        ui_state.artifacts = panel_artifacts
                    else:
                        logger.debug(
                            "[turn %d] No artifacts found in panel", turn_count
                        )

            consecutive_failures = 0  # reset on success

        except PostSubmissionObservationError:
            recovered_state = await _recover_and_check(page, config, current_message)
            if recovered_state is not None:
                ui_state = recovered_state
                consecutive_failures = 0
            else:
                try:
                    ui_state = await send_message(
                        page, current_message, config, timeout_override=response_timeout
                    )
                    consecutive_failures = 0
                except ResponseTimeoutError:
                    consecutive_failures += 1
                    if consecutive_failures >= config.retry.consecutive_turn_failures_limit:
                        raise ConsecutiveFailureEscalation(
                            f"{consecutive_failures} consecutive turn failures"
                        )
                    ui_state = UIState(
                        text="", errors=["Response timeout — no response received"]
                    )
        except TransientDOMError:
            consecutive_failures += 1
            if consecutive_failures >= config.retry.consecutive_turn_failures_limit:
                raise ConsecutiveFailureEscalation(
                    f"{consecutive_failures} consecutive turn failures"
                )
            await _recover_page(page, config)
            try:
                ui_state = await send_message(
                    page, current_message, config, timeout_override=response_timeout
                )
                consecutive_failures = 0
            except (TurnRecoverableError, ResponseTimeoutError) as inner_exc:
                consecutive_failures += 1
                if consecutive_failures >= config.retry.consecutive_turn_failures_limit:
                    raise ConsecutiveFailureEscalation(
                        f"{consecutive_failures} consecutive turn failures"
                    )
                if isinstance(inner_exc, ResponseTimeoutError):
                    ui_state = UIState(
                        text="", errors=["Response timeout — no response received"]
                    )
                else:
                    continue
        except ResponseTimeoutError:
            consecutive_failures += 1
            if consecutive_failures >= config.retry.consecutive_turn_failures_limit:
                raise ConsecutiveFailureEscalation(
                    f"{consecutive_failures} consecutive turn failures"
                )
            ui_state = UIState(text="", errors=["Response timeout — no response received"])
        except RunRecoverableError:
            raise

        send_elapsed = time.time() - send_start
        logger.info("[turn %d] send+wait: %.1fs", turn_count, send_elapsed)

        # Extract target session ID from URL
        if not target_session_id:
            try:
                chat_url = page.url
                match = re.search(r"/chat/(sess-[a-z0-9-]+)", chat_url, re.IGNORECASE)
                if match:
                    target_session_id = match.group(1)
                    logger.info(
                        "[turn %d] Captured target session ID: %s",
                        turn_count,
                        target_session_id,
                    )
            except Exception:
                pass

        turn_duration_ms = int((time.time() - turn_start) * 1000)

        # Record the conversation turn
        turn = ConversationTurn(
            turn_number=turn_count,
            user_message=current_message,
            target_response=ui_state.model_dump(),
            duration_ms=turn_duration_ms,
            timestamp=datetime.now(tz=UTC).isoformat(),
            user_ui_actions=[a.model_dump() for a in current_ui_actions],
        )
        conversation.append(turn)

        # Download artifacts detected in this turn
        if ui_state.artifacts:
            logger.info(
                "[turn %d] Downloading %d artifact(s)...",
                turn_count,
                len(ui_state.artifacts),
            )
            artifact_dest = run_dir / "artifacts" / f"turn-{turn_count}"
            downloaded_files = await _download_artifacts(
                page,
                [
                    {"name": a.name, "type": a.type, "url": a.url}
                    for a in ui_state.artifacts
                ],
                artifact_dest,
            )
            downloaded_names: set[str] = set()
            for dl in downloaded_files:
                artifacts_collected.append(
                    CollectedArtifact(
                        filename=dl["filename"],
                        collected_at_turn=turn_count,
                        path=dl["local_path"],
                    )
                )
                downloaded_names.add(dl["filename"])
                logger.info("[turn %d]   Downloaded: %s", turn_count, dl["filename"])

            # Record artifacts we couldn't download (for reference)
            for artifact in ui_state.artifacts:
                if artifact.name not in downloaded_names:
                    artifacts_collected.append(
                        CollectedArtifact(
                            filename=artifact.name,
                            collected_at_turn=turn_count,
                            path=artifact.url or "",
                        )
                    )
                    logger.debug(
                        "[turn %d]   Could not download: %s", turn_count, artifact.name
                    )

        # Capture inline charts as artifacts
        try:
            chart_dir = run_dir / "artifacts" / f"turn-{turn_count}" / "charts"
            charts = await capture_inline_charts(page, chart_dir, turn=turn_count)
            for chart in charts:
                artifacts_collected.append(
                    CollectedArtifact(
                        filename=chart["filename"],
                        collected_at_turn=turn_count,
                        path=chart["path"],
                    )
                )
        except Exception:
            pass

        # Turn summary
        logger.info("[turn %d] SUMMARY (%.1fs):", turn_count, turn_duration_ms / 1000)
        logger.info("[turn %d]   Response: %r", turn_count, ui_state.text[:100])
        if ui_state.artifacts:
            logger.info(
                "[turn %d]   Artifacts: %s",
                turn_count,
                ", ".join(a.name for a in ui_state.artifacts),
            )
        if ui_state.errors:
            logger.info(
                "[turn %d]   Errors: %s", turn_count, "; ".join(ui_state.errors)
            )
        if ui_state.form_elements:
            logger.info(
                "[turn %d]   Forms: %d element(s) detected",
                turn_count,
                len(ui_state.form_elements),
            )
        if ui_state.target_status_labels:
            logger.info(
                "[turn %d]   Agent labels: %s",
                turn_count,
                ", ".join(ui_state.target_status_labels[:5]),
            )
        logger.info(
            "[turn %d]   Total artifacts collected so far: %d",
            turn_count,
            len(artifacts_collected),
        )

        # Re-check timeout before next agent call (max_turns checked at top of loop)
        elapsed_after_turn = time.time() - start_time
        if elapsed_after_turn >= run_config.timeout_minutes * 60:
            logger.info(
                "[turn %d] STOP: timeout (%.1fs >= %ds)",
                turn_count,
                elapsed_after_turn,
                run_config.timeout_minutes * 60,
            )
            return _build_record(
                "timeout",
                run_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # Notify TUI that we are now waiting for the LLM user agent
        if state:
            state.update_run_turn(
                scenario.id,
                persona.id,
                trial=trial,
                turn=turn_count,
                max_turns=run_config.max_turns,
                detail="waiting for LLM...",
            )
            if tui_ctx:
                tui_ctx.refresh()

        # Get next response from user agent
        logger.info("=" * 60)
        logger.info(
            "[turn %d -> %d] USER AGENT THINKING...", turn_count, turn_count + 1
        )
        logger.info("=" * 60)
        logger.info(
            "[turn %d -> %d]   Input to agent — target response (%d chars): %r",
            turn_count,
            turn_count + 1,
            len(ui_state.text),
            ui_state.text[:150],
        )
        if ui_state.form_elements:
            logger.info(
                "[turn %d -> %d]   Input to agent — form elements: %s",
                turn_count,
                turn_count + 1,
                [f"{e.type}:{e.label}" for e in ui_state.form_elements],
            )
        if ui_state.artifacts:
            logger.info(
                "[turn %d -> %d]   Input to agent — artifacts present: %s",
                turn_count,
                turn_count + 1,
                [a.name for a in ui_state.artifacts],
            )
        if ui_state.errors:
            logger.info(
                "[turn %d -> %d]   Input to agent — errors: %s",
                turn_count,
                turn_count + 1,
                ui_state.errors,
            )

        turn_payload = UserAgentInput(
            ui_state=ui_state,
            run_meta=RunMeta(
                turn_number=turn_count,
                elapsed_seconds=int(time.time() - start_time),
            ),
        )

        agent_start = time.time()
        try:
            response = await agent.generate_response(turn_payload)
        except Exception as exc:
            logger.info(
                "[turn %d] STOP: system_error (user agent LLM failed: %s)",
                turn_count,
                exc,
            )
            return _build_record(
                "system_error",
                run_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )
        agent_elapsed = time.time() - agent_start
        logger.info("[turn %d] user-agent LLM: %.1fs", turn_count, agent_elapsed)

        # Update for next iteration
        current_message = response.message
        current_ui_actions = response.ui_actions
        current_decision = response.decision
        logger.info(
            "[turn %d -> %d] DECISION: decision=%s | message=%r",
            turn_count,
            turn_count + 1,
            current_decision,
            current_message[:120],
        )
        if response.reasoning:
            logger.info(
                "[turn %d -> %d] REASONING: %s",
                turn_count,
                turn_count + 1,
                response.reasoning,
            )


def _build_record(
    stop_reason: str,
    run_config: RunConfig,
    conversation: list[ConversationTurn],
    artifacts_collected: list[CollectedArtifact],
    start_time: float,
    target_session_id: str | None,
) -> RunRecord:
    """Assemble the final RunRecord from accumulated state."""
    duration_seconds = time.time() - start_time
    return RunRecord(
        config=run_config,
        target_session_id=target_session_id,
        outcome=RunOutcome(
            stop_reason=stop_reason,
            total_turns=len(conversation),
            duration_seconds=round(duration_seconds, 1),
        ),
        conversation=conversation,
        artifacts_collected=artifacts_collected,
    )


async def _download_artifacts(
    page: Page,
    artifacts: list[dict],
    run_dir: Path,
) -> list[dict]:
    """Download detected artifacts to disk using Playwright's download handling."""
    run_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict] = []
    download_count = sum(1 for a in artifacts if a.get("type") == "download")
    logger.info(
        "[download] Attempting to download %d artifact(s) to %s",
        download_count,
        run_dir,
    )

    dl_idx = 0
    for artifact in artifacts:
        if artifact.get("type") != "download":
            continue
        dl_idx += 1

        try:
            url = artifact.get("url")
            name = artifact.get("name", "file")
            logger.info(
                "[download]   [%d/%d] '%s' (url=%s)",
                dl_idx,
                download_count,
                name,
                url[:60] if url else "none",
            )

            if url:
                # Try clicking a link matching this URL or name
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
                    logger.debug("[download]   Clicking link element...")
                    async with page.expect_download(timeout=15000) as download_info:
                        await link.click()
                    download = await download_info.value
                    filename = Path(download.suggested_filename or name).name
                    dest_path = run_dir / filename
                    await download.save_as(str(dest_path))
                    downloaded.append(
                        {"filename": filename, "local_path": str(dest_path)}
                    )
                    logger.info("[download]   Saved: %s", dest_path)

                elif url.startswith(("http", "blob:")):
                    # Programmatic download via injected anchor
                    logger.debug(
                        "[download]   Injecting anchor for programmatic download..."
                    )
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
                    dest_path = run_dir / filename
                    await download.save_as(str(dest_path))
                    downloaded.append(
                        {"filename": filename, "local_path": str(dest_path)}
                    )
                    logger.info("[download]   Saved (programmatic): %s", dest_path)
                else:
                    logger.debug(
                        "[download]   No matching link and URL not http/blob — skipping"
                    )
            else:
                # No URL — try clicking a button by text match
                logger.debug(
                    "[download]   No URL — trying button text match for '%s'...", name
                )
                btn = (
                    page.locator("button")
                    .filter(has_text=re.compile(f"^{re.escape(name)}$", re.IGNORECASE))
                    .first
                )
                try:
                    btn_visible = await btn.is_visible(timeout=2000)
                except Exception:
                    btn_visible = False

                if btn_visible:
                    async with page.expect_download(timeout=15000) as download_info:
                        await btn.click()
                    download = await download_info.value
                    filename = Path(download.suggested_filename or name).name
                    dest_path = run_dir / filename
                    await download.save_as(str(dest_path))
                    downloaded.append(
                        {"filename": filename, "local_path": str(dest_path)}
                    )
                    logger.info("[download]   Saved (via button): %s", dest_path)
                else:
                    logger.debug(
                        "[download]   Button '%s' not visible — skipping", name
                    )

        except Exception as exc:
            logger.warning(
                "[download]   FAILED for '%s': %s", artifact.get("name", "?"), exc
            )

    logger.info(
        "[download] Downloaded %d/%d artifact(s)", len(downloaded), download_count
    )
    return downloaded
