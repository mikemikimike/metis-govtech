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

from .exceptions import (
    ConsecutiveFailureEscalation,
    PostSubmissionObservationError,
    ResponseTimeoutError,
    RunRecoverableError,
    TargetSessionEnded,
    TargetUnavailableError,
    TransientDOMError,
    TurnRecoverableError,
)
from .types import (
    ChosenAction,
    CollectedArtifact,
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
        trial: int = 1,
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
        self._trial = trial
        self._state = state
        self._tui_ctx = tui_ctx
        self._shutdown_event = shutdown_event

    async def run(self) -> RunRecord:
        """Execute the full simulation run."""
        run_config = self._run_config
        start_time = time.time()
        conversation: list[ConversationTurn] = []
        artifacts_collected: list[CollectedArtifact] = []
        turn_count = 0
        target_session_id: str | None = None

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
                    self._state.update_run_turn(
                        self._scenario.id,
                        run_config.persona,
                        trial=self._trial,
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

                # Send turn to target via runner
                try:
                    observation = await self._runner.send_turn(
                        current_message, current_actions
                    )
                    consecutive_failures = 0
                except PostSubmissionObservationError:
                    try:
                        await self._runner.recover()
                        observation = await self._runner.send_turn(current_message, [])
                        consecutive_failures = 0
                    except (TurnRecoverableError, ResponseTimeoutError) as inner:
                        consecutive_failures += 1
                        if consecutive_failures >= 2:
                            raise ConsecutiveFailureEscalation(
                                f"{consecutive_failures} consecutive turn failures"
                            ) from inner
                        observation = Observation(
                            errors=["Response timeout — no response received"]
                        )
                except TransientDOMError as exc:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        raise ConsecutiveFailureEscalation(
                            f"{consecutive_failures} consecutive turn failures"
                        ) from exc
                    await self._runner.recover()
                    try:
                        observation = await self._runner.send_turn(current_message, [])
                        consecutive_failures = 0
                    except (TurnRecoverableError, ResponseTimeoutError) as inner:
                        consecutive_failures += 1
                        if consecutive_failures >= 2:
                            raise ConsecutiveFailureEscalation(
                                f"{consecutive_failures} consecutive turn failures"
                            ) from inner
                        observation = Observation(
                            errors=["Response timeout — no response received"]
                        )
                except ResponseTimeoutError as exc:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        raise ConsecutiveFailureEscalation(
                            f"{consecutive_failures} consecutive turn failures"
                        ) from exc
                    observation = Observation(
                        errors=["Response timeout — no response received"]
                    )
                except TargetUnavailableError as exc:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        raise ConsecutiveFailureEscalation(
                            f"{consecutive_failures} consecutive turn failures"
                        ) from exc
                    observation = Observation(errors=[f"Target unavailable — {exc}"])
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
                    raise

                send_elapsed = time.time() - turn_start
                logger.info("[turn %d] send+wait: %.1fs", turn_count, send_elapsed)

                # Capture session ID
                if not target_session_id:
                    target_session_id = await self._runner.get_session_id()
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

                # Track artifacts
                for artifact in observation.artifacts:
                    artifacts_collected.append(
                        CollectedArtifact(
                            filename=artifact.name,
                            collected_at_turn=turn_count,
                            path=artifact.url or "",
                        )
                    )

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
                if observation.errors:
                    logger.info(
                        "[turn %d]   Errors: %s",
                        turn_count,
                        "; ".join(observation.errors),
                    )
                if observation.available_actions:
                    logger.info(
                        "[turn %d]   Actions available: %d",
                        turn_count,
                        len(observation.available_actions),
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
                    self._state.update_run_turn(
                        self._scenario.id,
                        run_config.persona,
                        trial=self._trial,
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

    def _build_record(
        self,
        stop_reason: str,
        conversation: list[ConversationTurn],
        artifacts_collected: list[CollectedArtifact],
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
            artifacts_collected=artifacts_collected,
        )
