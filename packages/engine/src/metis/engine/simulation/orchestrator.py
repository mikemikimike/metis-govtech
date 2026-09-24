"""Orchestrator — drives the turn loop, runner-agnostic.

Extracted from the former harness/_environment.py. The Orchestrator manages
stopping conditions, UserAgent interaction, conversation recording, and
RunRecord assembly without knowing anything about the transport layer.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from metis.core.logging import get_logger

from ._contract import (
    merge_withheld,
    validate_action_results,
    withhold_unstaged_uploads,
)
from ._fixture_artifacts import build_fixture_artifacts
from .artifact_summarizer import summarize_artifact
from .exceptions import (
    ConsecutiveFailureEscalation,
    ResponseTimeoutError,
    RunRecoverableError,
    TargetSessionEnded,
    TargetUnavailableError,
    TurnRecoverableError,
)
from .types import (
    ActionResult,
    Artifact,
    ChosenAction,
    ConversationTurn,
    Observation,
    RunConfig,
    RunMeta,
    RunOutcome,
    RunRecord,
    Scenario,
    TurnDiagnostics,
    UserAgentInput,
)

if TYPE_CHECKING:
    import threading
    from pathlib import Path

    from metis.engine.tui import SimulationState, TUIContext

    from .runner import Runner
    from .user_agent.agent import UserAgent

logger = get_logger()

_UNDELIVERED_REASON = (
    "No reply was captured for this turn — the target's response could not be read."
)


def _undelivered_reason(exc: Exception) -> str:
    """Persona-facing text for a turn whose ``send_turn`` raised.

    Preserves the two strings the ladder already produced where they remain
    accurate, and falls back to a neutral phrasing for the browser runner's
    two failure modes. ``PostSubmissionObservationError`` specifically means
    the message *did* reach the target and only the observation failed, so a
    reason claiming non-delivery would be a false first-hand report (P2).
    """
    if isinstance(exc, ResponseTimeoutError):
        return "Response timeout — no response received"
    if isinstance(exc, TargetUnavailableError):
        return f"Target unavailable — {exc}"
    return _UNDELIVERED_REASON


def _undelivered_observation(actions: list[ChosenAction], reason: str) -> Observation:
    """The uniform shape for a turn the runner could not complete.

    One ``succeeded=False`` row per submitted action, plus the same text as a
    ``response_notices`` entry so a consumer reading only notices still sees
    it. ``retryable`` is ``None`` — I2's "no opinion" — because the caller
    observed nothing first-hand and has no standing to advise a retry.
    ``available_actions`` stays ``None``: ``send_turn`` raised, so no page and
    no payload was ever inspected.

    I1 binds only what a *runner* returns, so this shape is voluntary. It
    exists so every downstream consumer sees one ``Observation`` shape whether
    the turn completed or not.
    """
    return Observation(
        response_notices=[reason],
        action_results=[
            ActionResult(action_index=index, succeeded=False, detail=reason)
            for index in range(len(actions))
        ],
        available_actions=None,
    )


class Orchestrator:
    """Drives the turn loop. Runner-agnostic."""

    def __init__(
        self,
        runner: Runner,
        agent: UserAgent,
        run_config: RunConfig,
        scenario: Scenario,
        run_dir: Path,
        fixtures_dir: Path,
        experiment_root: Path,
        fixture_artifacts: list[Artifact] | None = None,
        trial_index: int = 1,  # 1-based
        state: SimulationState | None = None,
        tui_ctx: TUIContext | None = None,
        shutdown_event: threading.Event | None = None,
    ) -> None:
        self._runner = runner
        self._agent = agent
        self._run_config = run_config
        self._scenario = scenario
        self._run_dir = run_dir
        self._fixtures_dir = fixtures_dir
        self._experiment_root = experiment_root
        self._fixture_artifacts = (
            fixture_artifacts
            if fixture_artifacts is not None
            else build_fixture_artifacts(
                run_config.fixtures, fixtures_dir, self._experiment_root
            )
        )
        # Staged fixtures by logical name — the enrichment loop swaps a
        # runner-emitted fixture stub for the SAME object recorded here.
        self._fixtures_by_name = {a.name: a for a in self._fixture_artifacts}
        self._trial_index = trial_index
        self._state = state
        self._tui_ctx = tui_ctx
        self._shutdown_event = shutdown_event

        # In-progress state mirrored here so a caller can still build a
        # record if run() raises. run() overwrites these on entry.
        self._conversation: list[ConversationTurn] = []
        self._artifacts_collected: list[Artifact] = []
        self._start_time: float = time.time()
        self._target_session_id: str | None = None

    async def run(self) -> RunRecord:
        """Execute the full simulation run."""
        run_config = self._run_config
        start_time = time.time()
        conversation: list[ConversationTurn] = []
        artifacts_collected: list[Artifact] = []
        turn_count = 0
        target_session_id: str | None = None

        # Mirror onto instance attributes so partial_record() can read them
        # if this coroutine raises before returning a record. The lists are
        # shared by reference, so later .append()s are visible via self.
        self._conversation = conversation
        self._artifacts_collected = artifacts_collected
        self._start_time = start_time
        self._target_session_id = None

        logger.info("=" * 60)
        logger.info("[sim] START: %s x %s", run_config.persona, run_config.scenario)
        logger.info(
            "[sim] Config: max_turns=%d, timeout=%d min, response_wait=%dms",
            run_config.max_turns,
            run_config.timeout_minutes,
            run_config.response_wait_ms,
        )
        logger.info("[sim] Scenario goal: %s", self._scenario.description[:120])
        logger.info("=" * 60)

        # Generate opening message
        logger.info("[sim] Generating opening message via LLM...")
        opening_start = time.time()
        try:
            opening = await self._agent.generate_opening()
        except Exception as exc:
            logger.info("[sim] STOP: system_error (opening LLM call failed: %s)", exc)
            return self._build_record(
                "system_error",
                conversation,
                artifacts_collected,
                start_time,
                None,
            )
        logger.info(
            "[sim] Opening message (%.1fs): %r",
            time.time() - opening_start,
            opening.message[:120],
        )

        current_message: str = opening.message
        current_actions: list[ChosenAction] = opening.actions
        current_decision: str = opening.decision
        consecutive_failures = 0

        try:
            await self._runner.setup(run_config)

            while True:
                if self._shutdown_event and self._shutdown_event.is_set():
                    logger.info("[turn %d] STOP: shutdown requested", turn_count)
                    return self._build_record(
                        "interrupted",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )

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

                if self._state:
                    self._state.mark_run_turn(
                        self._scenario.id,
                        run_config.persona,
                        trial_index=self._trial_index,
                        turn=turn_count,
                        max_turns=run_config.max_turns,
                        detail="sending message...",
                    )
                    if self._tui_ctx:
                        self._tui_ctx.refresh()

                # --- Stopping rule: max turns ---
                if turn_count > run_config.max_turns:
                    logger.info(
                        "[turn %d] STOP: max_turns reached (%d)",
                        turn_count,
                        run_config.max_turns,
                    )
                    return self._build_record(
                        "max_turns",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )

                # --- Stopping rule: timeout ---
                if elapsed_s >= run_config.timeout_minutes * 60:
                    logger.info(
                        "[turn %d] STOP: timeout (%.1fs >= %ds)",
                        turn_count,
                        elapsed_s,
                        run_config.timeout_minutes * 60,
                    )
                    return self._build_record(
                        "timeout",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )

                # --- Stopping rule: user abandoned ---
                if current_decision == "giving_up":
                    logger.info(
                        "[turn %d] STOP: user_abandoned (agent gave up)",
                        turn_count,
                    )
                    return self._build_record(
                        "user_abandoned",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )

                # --- Stopping rule: goal achieved ---
                if current_decision == "goal_achieved":
                    logger.info(
                        "[turn %d] STOP: goal_achieved",
                        turn_count,
                    )
                    return self._build_record(
                        "goal_achieved",
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

                # Caller-side rejection: an upload naming a fixture this
                # scenario never staged is never sent. The runner has no
                # standing to judge this — only the orchestrator knows what
                # was staged — and the report must not blame the target for
                # an action it never received.
                forwarded, withheld = withhold_unstaged_uploads(
                    current_actions,
                    set(self._fixtures_by_name),
                    set(run_config.fixtures),
                )

                # Send turn to target via runner
                try:
                    observation = await self._runner.send_turn(
                        current_message, forwarded
                    )
                    validate_action_results(observation, forwarded)
                    consecutive_failures = 0
                except TargetSessionEnded as exc:
                    logger.info(
                        "[turn %d] STOP: target_exhausted (%s)", turn_count, exc
                    )
                    return self._build_record(
                        "target_exhausted",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id or await self._runner.get_session_id(),
                    )
                except RunRecoverableError:
                    # Escalated by the run layer, never absorbed here. Listed
                    # before the turn-recoverable handler for the reader's
                    # sake — the two families are disjoint, so this is
                    # documentation rather than dispatch.
                    raise
                except (TurnRecoverableError, ResponseTimeoutError) as exc:
                    # I4: send_turn raised, so the caller cannot know whether
                    # the message landed. It is never re-sent for this turn.
                    # I3 hygiene for the *next* turn is now the runner's own
                    # business (docs/runner-contract.md) — see #361.
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        raise ConsecutiveFailureEscalation(
                            f"{consecutive_failures} consecutive turn failures"
                        ) from exc
                    reason = _undelivered_reason(exc)
                    logger.info("[turn %d] turn not completed: %s", turn_count, reason)
                    observation = _undelivered_observation(forwarded, reason)

                if withheld:
                    observation.action_results = merge_withheld(
                        observation.action_results, withheld
                    )

                send_elapsed = time.time() - turn_start
                logger.info("[turn %d] send+wait: %.1fs", turn_count, send_elapsed)

                # Capture session ID
                if not target_session_id:
                    target_session_id = await self._runner.get_session_id()
                    self._target_session_id = target_session_id
                    if target_session_id:
                        logger.info(
                            "[turn %d] Captured target session ID: %s",
                            turn_count,
                            target_session_id,
                        )

                turn_duration_ms = int((time.time() - turn_start) * 1000)

                # Record the conversation turn
                diagnostics: TurnDiagnostics | None = None
                if observation.discarded_message is not None:
                    diagnostics = TurnDiagnostics(
                        discarded_message=observation.discarded_message
                    )
                    logger.info(
                        "[turn %d]   Message not delivered by transport: %r",
                        turn_count,
                        observation.discarded_message[:80],
                    )
                # Stamp the turn onto each artifact and enrich downloads with a
                # digest + descriptions before the turn is recorded, so both
                # target_response and artifacts_collected carry enriched data.
                await self._enrich_observation_artifacts(
                    observation, turn_count, current_message
                )

                turn = ConversationTurn(
                    turn_number=turn_count,
                    user_message=current_message,
                    target_response=observation.model_dump(
                        exclude={"discarded_message"}
                    ),
                    duration_ms=turn_duration_ms,
                    timestamp=datetime.now(tz=UTC).isoformat(),
                    user_ui_actions=[a.model_dump() for a in current_actions],
                    diagnostics=diagnostics,
                )
                conversation.append(turn)

                # Track artifacts (already stamped with at_turn above)
                artifacts_collected.extend(observation.artifacts)

                # Turn summary
                logger.info(
                    "[turn %d] SUMMARY (%.1fs):",
                    turn_count,
                    turn_duration_ms / 1000,
                )
                logger.info(
                    "[turn %d]   Response: %r",
                    turn_count,
                    observation.text[:100],
                )
                if observation.artifacts:
                    logger.info(
                        "[turn %d]   Artifacts: %s",
                        turn_count,
                        ", ".join(a.name for a in observation.artifacts),
                    )
                if observation.response_notices:
                    logger.info(
                        "[turn %d]   Notices: %s",
                        turn_count,
                        "; ".join(observation.response_notices),
                    )
                # Unlike the persona prompt and the report, this log deliberately
                # includes withheld rows, marked as such: an operator reading
                # logs/ needs to see that METIS itself rejected an action, which
                # is often the actual bug.
                undelivered = [
                    row for row in observation.action_results if not row.succeeded
                ]
                if undelivered:
                    logger.info(
                        "[turn %d]   Actions not delivered: %s",
                        turn_count,
                        "; ".join(
                            f"[{row.action_index}]"
                            f"{' withheld:' if row.withheld else ''} {row.detail}"
                            for row in undelivered
                        ),
                    )
                if observation.available_actions:
                    logger.info(
                        "[turn %d]   Actions available: %d (%s)",
                        turn_count,
                        len(observation.available_actions),
                        ", ".join(
                            f"{slot.kind}:{slot.label!r}"
                            for slot in observation.available_actions
                        ),
                    )

                # Re-check stopping after turn
                if turn_count >= run_config.max_turns:
                    logger.info(
                        "[turn %d] STOP: max_turns reached (%d)",
                        turn_count,
                        run_config.max_turns,
                    )
                    return self._build_record(
                        "max_turns",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )

                elapsed_after_turn = time.time() - start_time
                if elapsed_after_turn >= run_config.timeout_minutes * 60:
                    logger.info(
                        "[turn %d] STOP: timeout (%.1fs >= %ds)",
                        turn_count,
                        elapsed_after_turn,
                        run_config.timeout_minutes * 60,
                    )
                    return self._build_record(
                        "timeout",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )

                # TUI update
                if self._state:
                    self._state.mark_run_turn(
                        self._scenario.id,
                        run_config.persona,
                        trial_index=self._trial_index,
                        turn=turn_count,
                        max_turns=run_config.max_turns,
                        detail="waiting for LLM...",
                    )
                    if self._tui_ctx:
                        self._tui_ctx.refresh()

                # Get next response from user agent
                logger.info("=" * 60)
                logger.info(
                    "[turn %d -> %d] USER AGENT THINKING...",
                    turn_count,
                    turn_count + 1,
                )
                logger.info("=" * 60)

                turn_payload = UserAgentInput(
                    observation=observation,
                    run_meta=RunMeta(
                        turn_number=turn_count,
                        elapsed_seconds=int(time.time() - start_time),
                    ),
                )

                agent_start = time.time()
                try:
                    response = await self._agent.generate_response(turn_payload)
                except Exception as exc:
                    logger.info(
                        "[turn %d] STOP: system_error (user agent LLM failed: %s)",
                        turn_count,
                        exc,
                    )
                    return self._build_record(
                        "system_error",
                        conversation,
                        artifacts_collected,
                        start_time,
                        target_session_id,
                    )
                agent_elapsed = time.time() - agent_start
                logger.info(
                    "[turn %d] user-agent LLM: %.1fs",
                    turn_count,
                    agent_elapsed,
                )

                # Update for next iteration
                current_message = response.message
                current_actions = response.actions
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
        finally:
            await self._runner.teardown()

    async def _enrich_observation_artifacts(
        self, observation: Observation, turn_count: int, current_message: str
    ) -> None:
        """Stamp + enrich this turn's observation artifacts, in place.

        A ``source="fixture"`` entry is a confirmed upload the runner echoed:
        swap the runner-emitted stub for the SAME worker-enriched registry
        object (matched by name), stamp the upload turn, and skip
        ``summarize_artifact`` — the fixture was described at build time, and
        re-summarizing would relabel it as a delivered target and re-hash a
        file already digested. Target downloads keep the stamp-and-summarize
        path. Swapping the registry object into ``observation.artifacts`` means
        the record folds one identity per fixture (deduped by id in
        ``_build_record``) and the UserAgent merges the enriched object.

        The swap discards the stub, so anything the stub alone knows has to be
        carried across it. ``external_id`` is the only such field: the registry
        object is built at staging time, before any target session exists, so
        the target's own file id can only come from the runner's echo.
        """
        for i, artifact in enumerate(observation.artifacts):
            if artifact.source == "fixture":
                registry = self._fixtures_by_name.get(artifact.name)
                if registry is None:
                    # Runner echoed a fixture name we never staged — record the
                    # un-enriched stub (no digest/description) but flag it, since
                    # it usually means a fixtures-dir / scenario-list mismatch.
                    logger.warning(
                        "[orchestrator] runner echoed unstaged fixture %r; "
                        "recording the un-enriched stub",
                        artifact.name,
                    )
                    registry = artifact
                if artifact.external_id is not None:
                    # Guarded, not unconditional: a runner that re-echoes an
                    # upload without an id must not blank the id an earlier turn
                    # established.
                    registry.external_id = artifact.external_id
                registry.at_turn = turn_count
                observation.artifacts[i] = registry
            else:
                artifact.at_turn = turn_count
                await summarize_artifact(
                    artifact,
                    experiment_root=self._experiment_root,
                    triggering_message=current_message,
                    turn_number=turn_count,
                )

    def _build_record(
        self,
        stop_reason: str,
        conversation: list[ConversationTurn],
        artifacts_collected: list[Artifact],
        start_time: float,
        target_session_id: str | None,
    ) -> RunRecord:
        """Assemble the final RunRecord from accumulated state."""
        duration_seconds = time.time() - start_time
        return RunRecord(
            config=self._run_config,
            target_session_id=target_session_id,
            outcome=RunOutcome(
                stop_reason=stop_reason,
                total_turns=len(conversation),
                duration_seconds=round(duration_seconds, 1),
            ),
            conversation=conversation,
            artifacts=list(
                {
                    a.id: a for a in (*self._fixture_artifacts, *artifacts_collected)
                }.values()
            ),
        )

    def partial_record(self, stop_reason: str) -> RunRecord:
        """Build a RunRecord from whatever progress this run has made.

        Used by the experiment worker when run() raises unexpectedly, so
        completed turns are preserved instead of discarded. total_turns is
        the number of turns recorded so far; duration is measured from the
        run's start.
        """
        return self._build_record(
            stop_reason,
            self._conversation,
            self._artifacts_collected,
            self._start_time,
            self._target_session_id,
        )
