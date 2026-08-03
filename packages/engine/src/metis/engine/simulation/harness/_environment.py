"""Turn loop orchestration — drives a simulation session to completion.

Instantiates the UserAgent directly (no subprocess), sends messages through
the Playwright page, enforces stopping conditions, and assembles the final
SessionRecord.
"""

import re
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page

from metis.core.logging import get_logger

from ..types import (
    ButtonClickAction,
    CollectedArtifact,
    ConversationTurn,
    ExperimentTask,
    FileUploadAction,
    FormFillAction,
    Persona,
    SessionConfig,
    SessionMeta,
    SessionOutcome,
    SessionRecord,
    TurnPayload,
    UIAction,
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

logger = get_logger()

_DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def run_simulation(
    page: Page,
    config: HarnessConfig,
    session_config: SessionConfig,
    persona: Persona,
    task: ExperimentTask,
    session_dir: Path,
    fixtures_dir: Path | None = None,
) -> SessionRecord:
    """Run a full simulation session: drive the turn loop and produce a SessionRecord.

    :param page: Playwright page already logged-in and on the chat screen.
    :param config: Harness config with timeouts and auth settings.
    :param session_config: Session-level config (max_turns, timeout_minutes).
    :param persona: The persona driving the simulated user.
    :param task: The experiment task defining the goal.
    :param session_dir: Pre-created session folder (``sessions/<task>-<persona>-<uuid>/``).
        Artifacts are written to ``session_dir/artifacts/`` during the turn loop.
    :param fixtures_dir: Directory containing fixture files for upload.
    :returns: A complete SessionRecord with conversation, outcome, and artifacts.
    """
    start_time = time.time()
    conversation: list[ConversationTurn] = []
    artifacts_collected: list[CollectedArtifact] = []
    turn_count = 0

    logger.info("=" * 60)
    logger.info("[sim] START: %s x %s", persona.id, task.id)
    logger.info(
        "[sim] Config: max_turns=%d, timeout=%d min, response_wait=%dms",
        session_config.max_turns,
        session_config.timeout_minutes,
        session_config.response_wait_ms or config.timeouts.response_wait_ms,
    )
    logger.info("[sim] Task goal: %s", task.description[:120])
    logger.info("=" * 60)

    # Instantiate user agent directly (no subprocess)
    logger.info("[sim] Initializing UserAgent (persona=%s)...", persona.id)
    agent = UserAgent(persona=persona, task=task)

    # Generate opening message
    logger.info("[sim] Generating opening message via LLM...")
    opening_start = time.time()
    opening = agent.generate_opening()
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
    dismiss_modals(page)

    # Track uploaded files to avoid duplicates
    uploaded_files: set[str] = set()

    # Capture target session ID from URL
    target_session_id: str | None = None

    # Initial state from opening
    current_message: str = opening.message
    current_ui_actions: list[UIAction] = opening.ui_actions
    current_action: str = opening.action

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
            session_config.timeout_minutes * 60,
        )

        # --- Stopping rule 1: max turns ---
        if turn_count > session_config.max_turns:
            logger.info(
                "[turn %d] STOP: max_turns reached (%d)",
                turn_count,
                session_config.max_turns,
            )
            return _build_record(
                "max_turns",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # --- Stopping rule 2: timeout ---
        if elapsed_s >= session_config.timeout_minutes * 60:
            logger.info(
                "[turn %d] STOP: timeout (%.1fs >= %ds)",
                turn_count,
                elapsed_s,
                session_config.timeout_minutes * 60,
            )
            return _build_record(
                "timeout",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # --- Stopping rule: user abandoned ---
        if current_action == "giving_up":
            logger.info("[turn %d] STOP: user_abandoned (agent gave up)", turn_count)
            return _build_record(
                "user_abandoned",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        # --- Stopping rule: goal achieved (with artifact capture window) ---
        if current_action == "goal_achieved":
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
                panel_artifacts = capture_artifacts_panel(page)
                if panel_artifacts:
                    logger.info(
                        "[turn %d] Found %d artifact(s) — downloading...",
                        turn_count,
                        len(panel_artifacts),
                    )
                    downloaded = _download_artifacts(
                        page,
                        [
                            {"name": a.name, "type": a.type, "url": a.url}
                            for a in panel_artifacts
                        ],
                        session_dir / "artifacts",
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
                page.wait_for_timeout(5000)

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
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        logger.info(
            "[turn %d] Action: %r | Message: %r",
            turn_count,
            current_action,
            current_message[:80],
        )

        # Detect actions that trigger long processing
        has_new_file_upload = any(
            isinstance(a, FileUploadAction) and a.file not in uploaded_files
            for a in current_ui_actions
        )
        has_form_submit = any(
            isinstance(a, ButtonClickAction)
            and re.search(
                r"submit|generate|run|start|create|analyze|confirm",
                a.selector,
                re.IGNORECASE,
            )
            for a in current_ui_actions
        )

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
                file_path = (fixtures_dir or _DEFAULT_FIXTURES_DIR) / action.file
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
                upload_file(page, file_path)
                uploaded_files.add(action.file)

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
                        page.locator(action.selector).first.click(timeout=5000)
                    else:
                        page.get_by_text(action.selector, exact=True).first.click(
                            timeout=5000
                        )
                    page.wait_for_timeout(1000)
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
                    is_model_select = page.locator(action.selector).first.evaluate(
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
                    tag_name = el.evaluate("e => e.tagName.toLowerCase()")
                    logger.debug("[turn %d]   Element tag: <%s>", turn_count, tag_name)
                    if tag_name == "select":
                        try:
                            el.select_option(label=fill_value)
                        except Exception:
                            el.select_option(fill_value)
                    elif tag_name == "input":
                        input_type = el.evaluate("e => e.type")
                        if input_type in ("radio", "checkbox"):
                            el.check()
                        else:
                            el.fill(fill_value)
                    elif tag_name == "textarea":
                        el.fill(fill_value)
                    else:
                        el.click()
                    page.wait_for_timeout(500)
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
            form_submitted = auto_fill_and_submit(page)
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
                page.wait_for_timeout(5000)
                poll_count = 0
                while time.time() * 1000 < processing_deadline:
                    still_processing = page.evaluate("""() => {
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
                            "[turn %d] Still processing after form submit (poll #%d)...",
                            turn_count,
                            poll_count,
                        )
                    page.wait_for_timeout(3000)
                logger.info(
                    "[turn %d] Form processing complete (polled %d times)",
                    turn_count,
                    poll_count,
                )
                page.wait_for_timeout(2000)
                ui_state = capture_ui_state(page)
            else:
                logger.info("[turn %d] Sending message to target...", turn_count)
                ui_state = send_message(
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
                    panel_artifacts = capture_artifacts_panel(page)
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
            return _build_record(
                "system_error",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        send_elapsed = time.time() - send_start
        logger.info("[turn %d] ⏱ send+wait: %.1fs", turn_count, send_elapsed)

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
                return _build_record(
                    "system_error",
                    session_config,
                    conversation,
                    artifacts_collected,
                    start_time,
                    target_session_id,
                )
        except Exception:
            logger.info(
                "[turn %d] STOP: system_error (page crashed — cannot read URL)",
                turn_count,
            )
            return _build_record(
                "system_error",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        turn_duration_ms = int((time.time() - turn_start) * 1000)

        # Record the conversation turn
        turn = ConversationTurn(
            turn_number=turn_count,
            user_message=current_message,
            system_response=ui_state.model_dump(),
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
            downloaded_files = _download_artifacts(
                page,
                [
                    {"name": a.name, "type": a.type, "url": a.url}
                    for a in ui_state.artifacts
                ],
                session_dir / "artifacts",
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
            chart_dir = session_dir / "artifacts" / "charts"
            charts = capture_inline_charts(page, chart_dir)
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
        if ui_state.agent_labels:
            logger.info(
                "[turn %d]   Agent labels: %s",
                turn_count,
                ", ".join(ui_state.agent_labels[:5]),
            )
        logger.info(
            "[turn %d]   Total artifacts collected so far: %d",
            turn_count,
            len(artifacts_collected),
        )

        # Re-check stopping conditions before next agent call
        if turn_count >= session_config.max_turns:
            logger.info(
                "[turn %d] STOP: max_turns reached (%d)",
                turn_count,
                session_config.max_turns,
            )
            return _build_record(
                "max_turns",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

        elapsed_after_turn = time.time() - start_time
        if elapsed_after_turn >= session_config.timeout_minutes * 60:
            logger.info(
                "[turn %d] STOP: timeout (%.1fs >= %ds)",
                turn_count,
                elapsed_after_turn,
                session_config.timeout_minutes * 60,
            )
            return _build_record(
                "timeout",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )

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

        turn_payload = TurnPayload(
            ui_state=ui_state,
            session_meta=SessionMeta(
                turn_number=turn_count,
                elapsed_seconds=int(time.time() - start_time),
            ),
        )

        agent_start = time.time()
        try:
            response = agent.generate_response(turn_payload)
        except Exception as exc:
            logger.info(
                "[turn %d] STOP: system_error (user agent LLM failed: %s)",
                turn_count,
                exc,
            )
            return _build_record(
                "system_error",
                session_config,
                conversation,
                artifacts_collected,
                start_time,
                target_session_id,
            )
        agent_elapsed = time.time() - agent_start
        logger.info("[turn %d] ⏱ user-agent LLM: %.1fs", turn_count, agent_elapsed)

        # Update for next iteration
        current_message = response.message
        current_ui_actions = response.ui_actions
        current_action = response.action
        logger.info(
            "[turn %d -> %d] DECISION: action=%s | message=%r",
            turn_count,
            turn_count + 1,
            current_action,
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
    session_config: SessionConfig,
    conversation: list[ConversationTurn],
    artifacts_collected: list[CollectedArtifact],
    start_time: float,
    target_session_id: str | None,
) -> SessionRecord:
    """Assemble the final SessionRecord from accumulated state.

    :param stop_reason: Why the simulation stopped (max_turns, timeout, etc.).
    :param session_config: The session configuration.
    :param conversation: List of recorded conversation turns.
    :param artifacts_collected: List of collected artifacts.
    :param start_time: Epoch timestamp when the simulation started.
    :param target_session_id: The target system's session ID extracted from URL, if found.
    :returns: A complete SessionRecord.
    """
    duration_seconds = time.time() - start_time
    return SessionRecord(
        config=session_config,
        target_session_id=target_session_id,
        outcome=SessionOutcome(
            stop_reason=stop_reason,
            total_turns=len(conversation),
            duration_seconds=round(duration_seconds, 1),
        ),
        conversation=conversation,
        artifacts_collected=artifacts_collected,
    )


def _download_artifacts(
    page: Page,
    artifacts: list[dict],
    session_dir: Path,
) -> list[dict]:
    """Download detected artifacts to disk using Playwright's download handling.

    :param page: The active Playwright page.
    :param artifacts: List of dicts with keys: name, type, url (optional).
    :param session_dir: Directory to save downloaded files.
    :returns: List of dicts with keys: filename, local_path.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict] = []
    download_count = sum(1 for a in artifacts if a.get("type") == "download")
    logger.info(
        "[download] Attempting to download %d artifact(s) to %s",
        download_count,
        session_dir,
    )

    for idx, artifact in enumerate(artifacts, 1):
        if artifact.get("type") != "download":
            continue

        try:
            url = artifact.get("url")
            name = artifact.get("name", "file")
            logger.info(
                "[download]   [%d/%d] '%s' (url=%s)",
                idx,
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
                link_exists = (
                    link.count() > 0
                    if hasattr(link, "count")
                    else link.is_visible(timeout=1000)
                )

                if link_exists:
                    logger.debug("[download]   Clicking link element...")
                    with page.expect_download(timeout=15000) as download_info:
                        link.click()
                    download = download_info.value
                    filename = Path(download.suggested_filename or name).name
                    dest_path = session_dir / filename
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
                    with page.expect_download(timeout=15000) as download_info:
                        page.evaluate(
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
                    download = download_info.value
                    filename = Path(download.suggested_filename or name).name
                    dest_path = session_dir / filename
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
                    btn_visible = btn.is_visible(timeout=2000)
                except Exception:
                    btn_visible = False

                if btn_visible:
                    with page.expect_download(timeout=15000) as download_info:
                        btn.click()
                    download = download_info.value
                    filename = Path(download.suggested_filename or name).name
                    dest_path = session_dir / filename
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
