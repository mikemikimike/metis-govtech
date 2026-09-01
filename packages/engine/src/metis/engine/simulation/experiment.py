"""Experiment runner — concurrent execution of scenario x persona runs.

Manages worker concurrency, retry logic, and result persistence.
Transport-specific concerns are delegated to Runner implementations.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from metis.core.console import console
from metis.core.logging import get_logger

from ._artifact_store import _save_artifacts
from .exceptions import RunRecoverableError
from .orchestrator import Orchestrator
from .types import (
    Experiment,
    Persona,
    RunConfig,
    RunFailure,
    RunOutcome,
    RunRecord,
    Scenario,
)
from .user_agent.agent import UserAgent

if TYPE_CHECKING:
    import threading

    from metis.engine.logging import LogRouter, OrchestrationLogger
    from metis.engine.tui import SimulationState, TUIContext

    from .runner import RunnerFactory

RunPlanItem = tuple[Scenario, Persona, int]

__all__ = [
    "RunPlanItem",
    "expand_run_plan",
    "run_experiment",
    "run_folder_name",
]

logger = get_logger()


def expand_run_plan(
    experiment: Experiment, personas_by_id: dict[str, Persona]
) -> list[RunPlanItem]:
    """Expand an experiment into scenario, persona, and zero-based trial items."""
    runs: list[RunPlanItem] = []
    for scenario in experiment.scenarios:
        for persona_ref in scenario.persona_refs:
            persona = personas_by_id.get(persona_ref)
            if not persona:
                available = ", ".join(personas_by_id.keys())
                raise ValueError(
                    f"Scenario '{scenario.id}': unknown persona_ref '{persona_ref}'. "
                    f"Available: {available}"
                )
            for trial in range(scenario.num_trials):
                runs.append((scenario, persona, trial))
    return runs


def run_folder_name(scenario: Scenario, persona: Persona, trial: int) -> str:
    """Return the stable folder name for a zero-based plan item."""
    trial_index = trial + 1
    pad = len(str(scenario.num_trials))
    return f"{scenario.id}-{persona.id}-{trial_index:0{pad}}"


def run_experiment(
    runner_factory: RunnerFactory,
    experiment: Experiment,
    personas_by_id: dict[str, Persona],
    fixtures_dir: Path,
    output_dir: Path | None = None,
    concurrency: int = 1,
    run_plan: list[RunPlanItem] | None = None,
    run_max_retries: int = 2,
    run_retry_delay_seconds: float = 5.0,
    # Optional hooks for TUI / structured-logging integration
    state: SimulationState | None = None,
    orchestration_logger: OrchestrationLogger | None = None,
    log_router: LogRouter | None = None,
    tui_ctx: TUIContext | None = None,
    shutdown_event: threading.Event | None = None,
) -> None:
    """Run a full experiment (all scenario x persona pairs).

    Sync entry point — delegates to the async orchestrator via asyncio.run().
    """
    asyncio.run(
        _run_experiment_async(
            runner_factory=runner_factory,
            experiment=experiment,
            personas_by_id=personas_by_id,
            fixtures_dir=fixtures_dir,
            output_dir=output_dir,
            concurrency=concurrency,
            run_plan=run_plan,
            run_max_retries=run_max_retries,
            run_retry_delay_seconds=run_retry_delay_seconds,
            state=state,
            orchestration_logger=orchestration_logger,
            log_router=log_router,
            tui_ctx=tui_ctx,
            shutdown_event=shutdown_event,
        )
    )


async def _run_experiment_async(
    runner_factory: RunnerFactory,
    experiment: Experiment,
    personas_by_id: dict[str, Persona],
    fixtures_dir: Path,
    output_dir: Path | None = None,
    concurrency: int = 1,
    run_plan: list[RunPlanItem] | None = None,
    run_max_retries: int = 2,
    run_retry_delay_seconds: float = 5.0,
    state: SimulationState | None = None,
    orchestration_logger: OrchestrationLogger | None = None,
    log_router: LogRouter | None = None,
    tui_ctx: TUIContext | None = None,
    shutdown_event: threading.Event | None = None,
) -> None:
    """Async experiment orchestrator with concurrent runner contexts."""
    runs = (
        run_plan
        if run_plan is not None
        else expand_run_plan(experiment, personas_by_id)
    )

    total_runs = len(runs)

    logger.info("=" * 60)
    logger.info("[experiment] STARTING EXPERIMENT")
    logger.info("[experiment]   Total runs: %d", total_runs)
    logger.info("[experiment]   Concurrency: %d worker(s)", concurrency)
    logger.info("[experiment]   Output dir: %s", output_dir or "results/ (default)")
    logger.info(
        "[experiment]   Scenarios: %s", ", ".join(s.id for s in experiment.scenarios)
    )
    logger.info("[experiment]   Personas: %s", ", ".join(personas_by_id.keys()))
    logger.info("=" * 60)

    # Distribute runs across workers (round-robin for balanced load)
    worker_slices = _distribute_runs(runs, concurrency)

    # Console lock for safe Rich output from concurrent workers
    console_lock = asyncio.Lock()

    # Shared across workers so scenario_started fires exactly once
    started_scenarios: set[str] = set()

    await runner_factory.start()
    try:
        active_worker_ids: list[int] = []
        worker_tasks = []
        for wid, slice_runs in enumerate(worker_slices):
            if slice_runs:
                active_worker_ids.append(wid)
                worker_tasks.append(
                    _worker(
                        worker_id=wid,
                        runner_factory=runner_factory,
                        run_slice=slice_runs,
                        total_runs=total_runs,
                        output_dir=output_dir,
                        fixtures_dir=fixtures_dir,
                        console_lock=console_lock,
                        started_scenarios=started_scenarios,
                        run_max_retries=run_max_retries,
                        run_retry_delay_seconds=run_retry_delay_seconds,
                        state=state,
                        orchestration_logger=orchestration_logger,
                        log_router=log_router,
                        tui_ctx=tui_ctx,
                        shutdown_event=shutdown_event,
                    )
                )

        raw_results = await asyncio.gather(*worker_tasks, return_exceptions=True)

        # Collect results, log any worker crashes
        all_records: list[RunRecord] = []
        for wid, result in zip(active_worker_ids, raw_results, strict=True):
            if isinstance(result, BaseException):
                logger.error("[experiment] Worker w%d crashed: %s", wid, result)
            else:
                all_records.extend(result)
    finally:
        await runner_factory.close()

    # Print summary (only in non-TUI mode; TUI mode prints via CLI after exiting)
    if not tui_ctx:
        console.print("\n\n========== SIMULATION SUMMARY ==========\n")
        for r in all_records:
            status = "PASS" if r.outcome.stop_reason == "goal_achieved" else "----"
            console.print(f"  [{status}] {r.config.persona} x {r.config.scenario}")
            console.print(
                f"         Turns: {r.outcome.total_turns}, "
                f"Duration: {r.outcome.duration_seconds}s, "
                f"Reason: {r.outcome.stop_reason}"
            )
    if not tui_ctx:
        console.print()
        achieved = sum(
            1 for r in all_records if r.outcome.stop_reason == "goal_achieved"
        )
        console.print(f"Goals achieved: {achieved}/{len(all_records)}")


async def _worker(
    worker_id: int,
    runner_factory: RunnerFactory,
    run_slice: list[tuple[Scenario, Persona, int]],
    total_runs: int,
    output_dir: Path | None,
    fixtures_dir: Path,
    console_lock: asyncio.Lock,
    started_scenarios: set[str],
    run_max_retries: int,
    run_retry_delay_seconds: float,
    state: SimulationState | None = None,
    orchestration_logger: OrchestrationLogger | None = None,
    log_router: LogRouter | None = None,
    tui_ctx: TUIContext | None = None,
    shutdown_event: threading.Event | None = None,
) -> list[RunRecord]:
    """One concurrent worker: creates a fresh runner per run for isolation."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(worker=f"w{worker_id}")

    logger.info(
        "[experiment] Worker w%d starting with %d run(s)", worker_id, len(run_slice)
    )

    try:
        records: list[RunRecord] = []
        for _idx, (scenario, persona, trial) in enumerate(run_slice):
            if shutdown_event and shutdown_event.is_set():
                logger.info(
                    "[experiment] Worker w%d stopping (shutdown requested)", worker_id
                )
                break

            trial_index = trial + 1
            trial_label = (
                f" (trial {trial_index}/{scenario.num_trials})"
                if scenario.num_trials > 1
                else ""
            )
            logger.info(
                "[experiment] RUN: %s x %s%s",
                persona.id,
                scenario.id,
                trial_label,
            )

            folder_name = run_folder_name(scenario, persona, trial)
            run_dir = (
                (output_dir / "runs" / folder_name)
                if output_dir
                else Path("results") / "runs" / folder_name
            )
            run_dir.mkdir(parents=True, exist_ok=True)

            # Bind run context for structured logging
            structlog.contextvars.bind_contextvars(
                scenario_id=scenario.id,
                persona_id=persona.id,
                trial=trial_index,
            )

            # Emit pre-run orchestration events (shared set — fires once across all workers)
            if scenario.id not in started_scenarios:
                started_scenarios.add(scenario.id)
                if orchestration_logger:
                    orchestration_logger.scenario_started(scenario.id)

            if orchestration_logger:
                orchestration_logger.run_started(
                    scenario.id,
                    persona.id,
                    trial=trial_index,
                    num_trials=scenario.num_trials,
                )
            if log_router:
                log_router.open_run(
                    scenario.id,
                    persona.id,
                    trial=trial_index,
                    num_trials=scenario.num_trials,
                )
            if state:
                state.start_run(
                    scenario.id, persona.id, trial=trial_index, worker_id=worker_id
                )

            async with console_lock:
                if tui_ctx:
                    tui_ctx.refresh()
                else:
                    console.print(f"  [w{worker_id}] {scenario.id} × {persona.id} ...")

            run_start = time.time()
            max_attempts = 1 + (
                scenario.max_run_retries
                if scenario.max_run_retries is not None
                else run_max_retries
            )
            prior_failures: list[RunFailure] = []
            record: RunRecord | None = None

            for attempt in range(1, max_attempts + 1):
                runner = await runner_factory.create(run_dir, fixtures_dir)

                try:
                    run_config = RunConfig(
                        persona=persona.id,
                        scenario=scenario.id,
                        metric_refs=scenario.metric_refs,
                        response_wait_ms=scenario.response_wait_ms,
                        fixtures=scenario.fixtures,
                    )
                    agent = UserAgent(persona=persona, scenario=scenario)
                    orchestrator = Orchestrator(
                        runner=runner,
                        agent=agent,
                        run_config=run_config,
                        scenario=scenario,
                        run_dir=run_dir,
                        fixtures_dir=fixtures_dir,
                        trial=trial_index,
                        state=state,
                        tui_ctx=tui_ctx,
                        shutdown_event=shutdown_event,
                    )
                    record = await orchestrator.run()
                    record.attempt_number = attempt
                    record.total_attempts = max_attempts
                    record.prior_failures = prior_failures
                    break
                except RunRecoverableError as exc:
                    duration_ms = int((time.time() - run_start) * 1000)
                    failure = RunFailure(
                        attempt_number=attempt,
                        failure_type=type(exc).__name__,
                        submission_phase="unknown",
                        turn_reached=0,
                        error_message=str(exc),
                        duration_ms=duration_ms,
                    )
                    prior_failures.append(failure)
                    logger.warning(
                        "[experiment] Worker w%d: %s on attempt %d/%d for %s × %s: %s",
                        worker_id,
                        type(exc).__name__,
                        attempt,
                        max_attempts,
                        scenario.id,
                        persona.id,
                        exc,
                    )

                    if attempt == max_attempts:
                        record = RunRecord(
                            config=RunConfig(
                                persona=persona.id,
                                scenario=scenario.id,
                                metric_refs=scenario.metric_refs,
                                fixtures=scenario.fixtures,
                            ),
                            target_session_id=None,
                            outcome=RunOutcome(
                                stop_reason="system_error",
                                total_turns=0,
                                duration_seconds=(time.time() - run_start),
                            ),
                            conversation=[],
                            artifacts_collected=[],
                            attempt_number=attempt,
                            total_attempts=max_attempts,
                            prior_failures=prior_failures,
                        )
                    else:
                        await asyncio.sleep(run_retry_delay_seconds)
                        run_start = time.time()

                except Exception as exc:
                    # Unexpected non-recoverable error — no retry
                    logger.error(
                        "[experiment] Worker w%d: unexpected crash for %s × %s: %s",
                        worker_id,
                        scenario.id,
                        persona.id,
                        exc,
                    )
                    record = RunRecord(
                        config=RunConfig(
                            persona=persona.id,
                            scenario=scenario.id,
                            metric_refs=scenario.metric_refs,
                            fixtures=scenario.fixtures,
                        ),
                        target_session_id=None,
                        outcome=RunOutcome(
                            stop_reason="system_error",
                            total_turns=0,
                            duration_seconds=(time.time() - run_start),
                        ),
                        conversation=[],
                        artifacts_collected=[],
                        attempt_number=attempt,
                        total_attempts=max_attempts,
                        prior_failures=prior_failures,
                    )
                    break

            assert record is not None  # always set: loop runs at least once

            # Emit post-run orchestration events
            if state:
                state.complete_run(
                    scenario.id,
                    persona.id,
                    trial=trial_index,
                    stop_reason=record.outcome.stop_reason,
                    duration_seconds=record.outcome.duration_seconds,
                )
            if orchestration_logger:
                orchestration_logger.run_completed(
                    scenario.id,
                    persona.id,
                    trial=trial_index,
                    num_trials=scenario.num_trials,
                    stop_reason=record.outcome.stop_reason,
                    total_turns=record.outcome.total_turns,
                    duration_seconds=record.outcome.duration_seconds,
                )
            if log_router:
                log_router.close_run(scenario.id, persona.id, trial=trial_index)

            # Check scenario completion
            if (
                state
                and orchestration_logger
                and _scenario_just_completed(state, scenario.id)
            ):
                sc = next(s for s in state.scenarios if s.scenario_id == scenario.id)
                passed = sum(1 for r in sc.runs if r.stop_reason == "goal_achieved")
                orchestration_logger.scenario_completed(
                    scenario.id, runs_passed=passed, runs_total=len(sc.runs)
                )

            async with console_lock:
                if tui_ctx:
                    tui_ctx.refresh()

            # Save run record to disk
            _save_run_record(record, run_dir)
            logger.info("[experiment] Saved record: %s", run_dir / "record.json")

            # Build per-turn timing breakdown
            timing_parts: list[str] = []
            for t in record.conversation:
                timing_parts.append(f"t{t.turn_number}={t.duration_ms / 1000:.0f}s")
            timing_str = f" [{', '.join(timing_parts)}]" if timing_parts else ""

            if not tui_ctx:
                async with console_lock:
                    console.print(
                        f"  [w{worker_id}] {scenario.id} × {persona.id} — "
                        f"{record.outcome.stop_reason}, "
                        f"{record.outcome.total_turns} turns, "
                        f"{record.outcome.duration_seconds:.0f}s{timing_str}"
                    )

            logger.info(
                "[experiment] Result: stop_reason=%s, turns=%d, duration=%.1fs",
                record.outcome.stop_reason,
                record.outcome.total_turns,
                record.outcome.duration_seconds,
            )

            if record.artifacts_collected:
                manifest = _save_artifacts(record, run_dir)
                logger.info(
                    "[experiment] Artifacts: %d saved (target_session: %s)",
                    len(manifest["artifacts"]),
                    manifest["session_id"],
                )

            records.append(record)

        return records
    finally:
        structlog.contextvars.unbind_contextvars("worker")


def _distribute_runs(
    runs: list[tuple[Scenario, Persona, int]],
    concurrency: int,
) -> list[list[tuple[Scenario, Persona, int]]]:
    """Distribute runs across workers using round-robin."""
    slices: list[list[tuple[Scenario, Persona, int]]] = [[] for _ in range(concurrency)]
    for i, run in enumerate(runs):
        slices[i % concurrency].append(run)
    return slices


def _save_run_record(record: RunRecord, run_dir: Path) -> None:
    """Save a run record as record.json inside the run folder."""
    filepath = run_dir / "record.json"
    filepath.write_text(json.dumps(record.model_dump(), indent=2))


def _scenario_just_completed(state: SimulationState, scenario_id: str) -> bool:
    """Return True when every run in the given scenario is now complete/failed."""
    sc = next((s for s in state.scenarios if s.scenario_id == scenario_id), None)
    return sc is not None and sc.phase == "completed"
