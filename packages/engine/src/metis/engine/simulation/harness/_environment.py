"""Turn loop orchestration — drives a simulation run to completion.

Instantiates the UserAgent directly (no subprocess), sends messages through
the Playwright page, enforces stopping conditions, and assembles the final
RunRecord.
"""

from __future__ import annotations

import contextlib
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import Page

from metis.core.logging import get_logger

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
    UserAgentInput,
)
from ..user_agent.agent import UserAgent
from ._action_filter import ActionIntent, SkipReason, filter_actions
from ._auth import dismiss_modals
from ._config import HarnessConfig
from ._page_actions import auto_fill_and_submit, send_message, upload_file
from ._protocol import (
    GuardFailed,
    do_action,
    guard_element,
    stabilize,
    wait_until_settled,
)
from ._ui_capture import (
    capture_artifacts_panel,
    capture_inline_charts,
    capture_ui_state,
)

if TYPE_CHECKING:
    from metis.engine.tui import SimulationState, TUIContext

logger = get_logger()


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

    # Track consecutive failures per action key for hard-stop
    consecutive_failures: dict[str, int] = {}

    # Capture target session ID from URL
    target_session_id: str | None = None

    def _finish(stop_reason: str) -> RunRecord:
        return _build_record(
            stop_reason,
            run_config,
            conversation,
            artifacts_collected,
            start_time,
            target_session_id,
        )

    # Initial state from opening
    current_message: str = opening.message
    current_ui_actions: list[UIAction] = opening.ui_actions
    current_decision: str = opening.decision

    # Turn loop
    while True:
        turn_count += 1
        turn_start = time.time()
        elapsed_s = time.time() - start_time

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
            return _finish("max_turns")

        # --- Stopping rule 2: timeout ---
        if elapsed_s >= run_config.timeout_minutes * 60:
            logger.info(
                "[turn %d] STOP: timeout (%.1fs >= %ds)",
                turn_count,
                elapsed_s,
                run_config.timeout_minutes * 60,
            )
            return _finish("timeout")

        # --- Stopping rule: user abandoned ---
        if current_decision == "giving_up":
            logger.info("[turn %d] STOP: user_abandoned (agent gave up)", turn_count)
            return _finish("user_abandoned")

        # --- Stopping rule: goal achieved (with single artifact capture attempt) ---
        if current_decision == "goal_achieved":
            logger.info(
                "[turn %d] STOP: goal_achieved",
                turn_count,
            )
            # Only attempt artifact capture if we already found some during the run
            if artifacts_collected:
                logger.info(
                    "[turn %d] Collected %d artifact(s) during run",
                    turn_count,
                    len(artifacts_collected),
                )
            else:
                # Single attempt — don't loop for 2 minutes
                panel_artifacts = capture_artifacts_panel(page)
                if panel_artifacts:
                    logger.info(
                        "[turn %d] Found %d artifact(s) in final check — downloading...",
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
                        turn=turn_count,
                    )
                    for dl in downloaded:
                        artifacts_collected.append(
                            CollectedArtifact(
                                filename=dl["filename"],
                                collected_at_turn=turn_count,
                                path=dl["local_path"],
                            )
                        )

            return _finish("goal_achieved")

        logger.info(
            "[turn %d] Decision: %r | Message: %r",
            turn_count,
            current_decision,
            current_message[:80],
        )

        # --- Action validation layer (one place, one policy) ---
        available_files = (
            [f.name for f in fixtures_dir.iterdir() if f.is_file()]
            if fixtures_dir.exists()
            else []
        )
        filter_result = filter_actions(
            current_ui_actions,
            uploaded_files=uploaded_files,
            available_files=available_files,
        )

        # Detect actions that trigger long processing (from validated set)
        has_new_file_upload = any(
            va.intent == ActionIntent.upload for va in filter_result.actions
        )
        has_form_submit = any(
            va.intent == ActionIntent.submit for va in filter_result.actions
        )

        # Report skipped actions as feedback
        turn_action_feedback: list[str] = []
        for sk in filter_result.skipped:
            if sk.reason == SkipReason.duplicate_upload:
                turn_action_feedback.append(
                    f"upload '{sk.action.file}': skipped — already uploaded"  # type: ignore[union-attr]
                )
            elif sk.reason == SkipReason.file_not_found:
                turn_action_feedback.append(
                    f"upload '{sk.action.file}': FAILED — file not found. "  # type: ignore[union-attr]
                    f"Available: {sk.detail}"
                )

        # --- action dispatch ---
        has_submit_action = False

        for validated in filter_result.actions:
            action = validated.action

            if validated.intent == ActionIntent.upload:
                assert isinstance(action, FileUploadAction)
                action_key = f"upload:{action.file}"
                file_path = fixtures_dir / action.file
                upload_result = upload_file(page, file_path)
                if upload_result.succeeded and upload_result.effect_verified:
                    uploaded_files.add(action.file)
                    consecutive_failures.pop(action_key, None)
                else:
                    msg = f"upload '{action.file}': "
                    if not upload_result.succeeded:
                        msg += f"FAILED — {upload_result.error}"
                    else:
                        msg += "completed but file chip not visible in UI"
                    turn_action_feedback.append(msg)
                    consecutive_failures[action_key] = (
                        consecutive_failures.get(action_key, 0) + 1
                    )

            elif validated.intent in (ActionIntent.click, ActionIntent.submit):
                assert isinstance(action, ButtonClickAction)
                action_key = f"click:{action.selector}"
                intent_name = (
                    "submit_form"
                    if validated.intent == ActionIntent.submit
                    else "click_button"
                )
                is_css = bool(re.search(r"[.#\[\]=:>~+]", action.selector))
                selector = action.selector

                try:
                    guard_element(page, selector, action=intent_name)
                except GuardFailed as exc:
                    turn_action_feedback.append(
                        f"click '{selector}': BLOCKED — {exc.reason}"
                    )
                    consecutive_failures[action_key] = (
                        consecutive_failures.get(action_key, 0) + 1
                    )
                    continue

                # Snapshot page text before submit to detect stale state
                pre_click_text = ""
                if validated.intent == ActionIntent.submit:
                    with contextlib.suppress(Exception):
                        pre_click_text = page.locator("main").first.inner_text(
                            timeout=2000
                        )

                def _do_click(sel: str = selector, css: bool = is_css) -> None:
                    if css:
                        page.locator(sel).first.click(timeout=5000)
                    else:
                        page.get_by_text(sel, exact=True).first.click(timeout=5000)

                result = do_action(page, intent=intent_name, act=_do_click)
                if result.succeeded:
                    stabilize(page, "post-click settle", 500)
                    consecutive_failures.pop(action_key, None)
                    if validated.intent == ActionIntent.submit:
                        has_submit_action = True
                        # Stale-state detection: page should change after submit
                        try:
                            post_click_text = page.locator("main").first.inner_text(
                                timeout=2000
                            )
                        except Exception:
                            post_click_text = ""
                        if (
                            pre_click_text
                            and post_click_text
                            and pre_click_text == post_click_text
                        ):
                            turn_action_feedback.append(
                                f"submit '{selector}': clicked but page unchanged"
                                " — form may require unfilled fields"
                            )
                            consecutive_failures[action_key] = (
                                consecutive_failures.get(action_key, 0) + 1
                            )
                else:
                    visible = ""
                    if result.page_context and result.page_context.visible_elements:
                        visible = " Visible: " + ", ".join(
                            result.page_context.visible_elements[:5]
                        )
                    turn_action_feedback.append(
                        f"click '{action.selector}': FAILED — {result.error}.{visible}"
                    )
                    consecutive_failures[action_key] = (
                        consecutive_failures.get(action_key, 0) + 1
                    )

            elif validated.intent == ActionIntent.fill:
                assert isinstance(action, FormFillAction)
                action_key = f"fill:{action.selector}"
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

                _fill_selector = action.selector
                _fill_value = fill_value

                def _do_form_fill(
                    selector: str = _fill_selector,
                    value: str = _fill_value,
                ) -> None:
                    el = page.locator(selector).first
                    tag_name = el.evaluate("e => e.tagName.toLowerCase()")
                    if tag_name == "select":
                        try:
                            el.select_option(label=value)
                        except Exception:
                            el.select_option(value)
                    elif tag_name == "input":
                        input_type = await el.evaluate("e => e.type")
                        if input_type in ("radio", "checkbox"):
                            # Orca hides inputs with sr-only; click wrapping label instead
                            label = el.locator("xpath=ancestor::label")
                            try:
                                if label.count() > 0 and label.first.is_visible(
                                    timeout=1000
                                ):
                                    label.first.click(force=True)
                                else:
                                    el.check(force=True)
                            except Exception:
                                el.check(force=True)
                        else:
                            el.fill(value)
                    elif tag_name == "textarea":
                        el.fill(value)
                    else:
                        el.click()

                try:
                    guard_element(page, action.selector, action="fill_form")
                except GuardFailed as exc:
                    turn_action_feedback.append(
                        f"form_fill '{action.selector}': BLOCKED — {exc.reason}"
                    )
                    consecutive_failures[action_key] = (
                        consecutive_failures.get(action_key, 0) + 1
                    )
                    continue

                result = do_action(page, intent="fill_form", act=_do_form_fill)
                if result.succeeded:
                    stabilize(page, "form value committed", 300)
                    consecutive_failures.pop(action_key, None)
                else:
                    visible = ""
                    if result.page_context and result.page_context.visible_elements:
                        visible = " Visible: " + ", ".join(
                            result.page_context.visible_elements[:5]
                        )
                    turn_action_feedback.append(
                        f"form_fill '{action.selector}': FAILED — {result.error}.{visible}"
                    )
                    consecutive_failures[action_key] = (
                        consecutive_failures.get(action_key, 0) + 1
                    )

        # Hard-stop if any action has failed 3 consecutive turns
        for key, count in consecutive_failures.items():
            if count >= 3:
                logger.info(
                    "[turn %d] STOP: user_abandoned — action '%s' failed %d consecutive turns",
                    turn_count,
                    key,
                    count,
                )
                return _finish("user_abandoned")

        # Auto-fill if the user agent didn't provide form submit actions
        if not has_form_submit:
            logger.debug(
                "[turn %d] No form submit in UI actions — trying auto_fill_and_submit...",
                turn_count,
            )
            form_submitted = await auto_fill_and_submit(page)
            if form_submitted:
                has_form_submit = True
                has_submit_action = True

        # Decide: wait for form processing (submit succeeded) or send message
        actually_awaiting = has_submit_action

        # After file upload, Orca may auto-start processing. Wait for it to
        # settle before sending the message to avoid cancelling its response.
        if has_new_file_upload and not actually_awaiting:
            logger.debug("[turn %d] Waiting for post-upload settle...", turn_count)
            stabilize(page, "post-upload settle", 2000)
            wait_until_settled(page, idle_timeout_ms=10000)

        # Determine response timeout
        response_timeout: int | None = None
        if has_new_file_upload or actually_awaiting:
            response_timeout = max(config.timeouts.response_wait_ms, 180000)

        # Send message or wait for form processing
        try:
            if actually_awaiting:
                stabilize(page, "initial form processing delay", 3000)
                wait_result = wait_until_settled(page)
                if not wait_result.satisfied:
                    turn_action_feedback.append(
                        "form processing hit hard ceiling — response may be incomplete"
                    )
                stabilize(page, "post-processing settle", 1000)
                ui_state = capture_ui_state(page)
            else:
                # Dismiss modal if present before sending
                try:
                    has_modal = page.evaluate(
                        "() => !!document.querySelector('[role=\"dialog\"]')"
                    )
                    if has_modal:
                        dismiss_modals(page)
                except Exception:
                    pass
                ui_state = send_message(
                    page,
                    current_message,
                    config,
                    timeout_override=response_timeout,
                )

            # Check artifacts panel if response contains download links/signals
            if not ui_state.artifacts:
                # Only check if there's a strong signal: actual download-related
                # language or we just uploaded a file / submitted a form
                has_download_signal = bool(
                    re.search(
                        r"download|export|attached|here(?:'|')s (?:the|your) file",
                        ui_state.text,
                        re.IGNORECASE,
                    )
                )
                had_processing = has_new_file_upload or actually_awaiting
                if has_download_signal or had_processing:
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

        except Exception as exc:
            # --- Stopping rule: system error ---
            logger.info("[turn %d] STOP: system_error (%s)", turn_count, exc)
            return _finish("system_error")

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

        # Detect auth loss
        try:
            url = page.url
            if "login" in url or "auth" in url:
                logger.info(
                    "[turn %d] STOP: system_error (auth lost — URL contains login/auth: %s)",
                    turn_count,
                    url,
                )
                return _finish("system_error")
        except Exception:
            logger.info(
                "[turn %d] STOP: system_error (page crashed — cannot read URL)",
                turn_count,
            )
            return _finish("system_error")

        turn_duration_ms = int((time.time() - turn_start) * 1000)
        logger.info(
            "[turn %d] Done (%.1fs) response=%d chars, artifacts=%d, errors=%d",
            turn_count,
            turn_duration_ms / 1000,
            len(ui_state.text) if ui_state else 0,
            len(ui_state.artifacts) if ui_state and ui_state.artifacts else 0,
            len(ui_state.errors) if ui_state and ui_state.errors else 0,
        )

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

        # Download artifacts detected in this turn (skip already-collected ones)
        already_collected_names = {a.filename for a in artifacts_collected}
        new_artifacts = [
            a for a in ui_state.artifacts if a.name not in already_collected_names
        ]
        if new_artifacts:
            logger.info(
                "[turn %d] Downloading %d new artifact(s) (%d already collected)...",
                turn_count,
                len(new_artifacts),
                len(ui_state.artifacts) - len(new_artifacts),
            )
            downloaded_files = await _download_artifacts(
                page,
                [{"name": a.name, "type": a.type, "url": a.url} for a in new_artifacts],
                run_dir / "artifacts",
                turn=turn_count,
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
            for artifact in new_artifacts:
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
            chart_dir = run_dir / "artifacts" / "charts"
            charts = capture_inline_charts(page, chart_dir, turn=turn_count)
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

        elapsed_after_turn = time.time() - start_time
        if elapsed_after_turn >= run_config.timeout_minutes * 60:
            logger.info(
                "[turn %d] STOP: timeout (%.1fs >= %ds)",
                turn_count,
                elapsed_after_turn,
                run_config.timeout_minutes * 60,
            )
            return _finish("timeout")

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

        if turn_action_feedback:
            logger.info(
                "[turn %d -> %d]   Input to agent — action feedback: %s",
                turn_count,
                turn_count + 1,
                turn_action_feedback,
            )

        turn_payload = UserAgentInput(
            ui_state=ui_state,
            run_meta=RunMeta(
                turn_number=turn_count,
                elapsed_seconds=int(time.time() - start_time),
            ),
            action_feedback=turn_action_feedback,
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
            return _finish("system_error")
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
    turn: int = 0,
) -> list[dict]:
    """Download detected artifacts to disk using Playwright's download handling.

    :param page: The active Playwright page.
    :param artifacts: List of dicts with keys: name, type, url (optional).
    :param run_dir: Base directory for artifacts.
    :param turn: Current turn number (used for subdirectory to avoid overwrites).
    :returns: List of dicts with keys: filename, local_path.
    """
    dest_dir = run_dir / f"turn-{turn}" if turn > 0 else run_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
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
                    dest_path = dest_dir / filename
                    download.save_as(str(dest_path))
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
                    dest_path = dest_dir / filename
                    download.save_as(str(dest_path))
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
                    dest_path = dest_dir / filename
                    download.save_as(str(dest_path))
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
