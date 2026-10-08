"""Experiment runner — concurrent execution of explicit Tasks and Trials.

Manages worker concurrency, retry logic, and result persistence.
Transport-specific concerns are delegated to Runner implementations.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import structlog

from metis.core.console import console
from metis.core.logging import get_logger

from ._artifact_store import _save_artifacts, quarantine_stale_artifacts
from ._fixture_artifacts import build_fixture_artifacts
from .artifact_summarizer import resolve_fixture_descriptions
from .exceptions import RunRecoverableError
from .orchestrator import Orchestrator
from .types import (
    Persona,
    RunConfig,
    RunFailure,
    RunOutcome,
    RunRecord,
    Scenario,
    Specification,
)
from .user_agent.agent import UserAgent

if TYPE_CHECKING:
    import threading

    from metis.engine.logging import LogRouter, OrchestrationLogger
    from metis.engine.tui import SimulationState, TUIContext

    from .runner import RunnerFactory


class RunPlanItem(NamedTuple):
    """One planned run: a scenario × persona pair at a specific trial.

    ``trial_index`` is 1-based: the first trial is 1 (not 0). It numbers the
    repeated trials of a scenario/persona pair (1..``scenario.num_trials``) and
    is used verbatim in log filenames, run-folder names, and TUI/log output.
    """

    scenario: Scenario
    persona: Persona
    trial_index: int  # 1-based: first trial is 1


__all__ = [
    "RunPlanItem",
    "expand_run_plan",
    "run_experiment",
    "run_folder_name",
]

logger = get_logger()


def expand_run_plan(
    specification: Specification, personas_by_id: dict[str, Persona]
) -> list[RunPlanItem]:
    """Expand an experiment into scenario, persona, and 1-based trial items."""
    runs: list[RunPlanItem] = []
    for scenario in specification.resolved_tasks():
        for persona_ref in scenario.persona_refs:
            persona = personas_by_id.get(persona_ref)
            if not persona:
                available = ", ".join(personas_by_id.keys())
                raise ValueError(
                    f"Scenario '{scenario.id}': unknown persona_ref '{persona_ref}'. "
                    f"Available: {available}"
                )
            for trial_index in range(1, scenario.num_trials + 1):
                runs.append(RunPlanItem(scenario, persona, trial_index))
    return runs


def run_folder_name(scenario: Scenario, persona: Persona, trial_index: int) -> str:
    """Return the stable run-folder name. ``trial_index`` is 1-based (first trial is 1)."""
    pad = len(str(scenario.num_trials))
    return f"{scenario.task_id or scenario.id}-{persona.id}-{trial_index:0{pad}}"


def run_experiment(
    runner_factory: RunnerFactory,
    specification: Specification,
    personas_by_id: dict[str, Persona],
    fixtures_dir: Path,
    *,
    run_plan: list[RunPlanItem],
    output_dir: Path | None = None,
    concurrency: int = 1,
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
            specification=specification,
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
    specification: Specification,
    personas_by_id: dict[str, Persona],
    fixtures_dir: Path,
    run_plan: list[RunPlanItem],
    output_dir: Path | None = None,
    concurrency: int = 1,
    run_max_retries: int = 2,
    run_retry_delay_seconds: float = 5.0,
    state: SimulationState | None = None,
    orchestration_logger: OrchestrationLogger | None = None,
    log_router: LogRouter | None = None,
    tui_ctx: TUIContext | None = None,
    shutdown_event: threading.Event | None = None,
) -> None:
    """Async experiment orchestrator with concurrent runner contexts."""
    total_runs = len(run_plan)

    logger.info("=" * 60)
    logger.info("[experiment] STARTING EXPERIMENT")
    logger.info("[experiment]   Total runs: %d", total_runs)
    logger.info("[experiment]   Concurrency: %d worker(s)", concurrency)
    logger.info("[experiment]   Output dir: %s", output_dir or "results/ (default)")
    logger.info(
        "[experiment]   Scenarios: %s", ", ".join(s.id for s in specification.scenarios)
    )
    logger.info("[experiment]   Personas: %s", ", ".join(personas_by_id.keys()))
    logger.info("=" * 60)

    # Distribute runs across workers (round-robin for balanced load)
    runs_per_worker: list[list[RunPlanItem]] = _distribute_runs(run_plan, concurrency)

    # Console lock for safe Rich output from concurrent workers
    console_lock = asyncio.Lock()

    # Shared across workers so scenario_started fires exactly once
    started_scenarios: set[str] = set()

    # Resolve each undescribed fixture's content_description exactly once, here,
    # before workers fan out — a fixture's content is invariant across scenarios
    # and runs, so it is summarized once per experiment (spec §6), not per run or
    # per attempt. Workers thread this complete map into their per-run Artifact
    # builds; those builds never re-summarize.
    all_fixture_names = [name for task in specification.tasks for name in task.fixtures]
    experiment_root = output_dir if output_dir is not None else Path("results")
    resolved_fixture_descriptions = await resolve_fixture_descriptions(
        all_fixture_names,
        fixtures_dir,
        experiment_root,
        specification.fixture_content_descriptions,
    )

    await runner_factory.start()
    try:
        active_worker_ids: list[int] = []
        worker_tasks = []
        for wid, worker_runs in enumerate(runs_per_worker):
            if worker_runs:
                active_worker_ids.append(wid)
                worker_tasks.append(
                    _worker(
                        worker_id=wid,
                        runner_factory=runner_factory,
                        worker_runs=worker_runs,
                        experiment_root=experiment_root,
                        fixtures_dir=fixtures_dir,
                        fixture_content_descriptions=resolved_fixture_descriptions,
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
    worker_runs: list[RunPlanItem],
    experiment_root: Path,
    fixtures_dir: Path,
    fixture_content_descriptions: dict[str, str],
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
        "[experiment] Worker w%d starting with %d run(s)", worker_id, len(worker_runs)
    )

    try:
        records: list[RunRecord] = []
        for scenario, persona, trial_index in worker_runs:
            task_id = scenario.task_id or scenario.id
            if shutdown_event and shutdown_event.is_set():
                logger.info(
                    "[experiment] Worker w%d stopping (shutdown requested)", worker_id
                )
                break

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

            folder_name = run_folder_name(scenario, persona, trial_index)
            run_dir = experiment_root / "runs" / folder_name
            run_dir.mkdir(parents=True, exist_ok=True)

            # Bind run context for structured logging
            structlog.contextvars.bind_contextvars(
                scenario_id=scenario.id,
                task_id=task_id,
                persona_id=persona.id,
                trial_index=trial_index,
            )

            # Emit pre-run orchestration events (shared set — fires once across all workers)
            if task_id not in started_scenarios:
                started_scenarios.add(task_id)
                if orchestration_logger:
                    orchestration_logger.scenario_started(task_id)

            if orchestration_logger:
                orchestration_logger.run_started(
                    task_id,
                    persona.id,
                    trial_index=trial_index,
                    num_trials=scenario.num_trials,
                )
            if log_router:
                log_router.open_run(
                    task_id,
                    persona.id,
                    trial_index=trial_index,
                    num_trials=scenario.num_trials,
                    run_dir=run_dir,
                )
            if state:
                state.mark_run_started(
                    task_id,
                    persona.id,
                    trial_index=trial_index,
                    worker_id=worker_id,
                )

            async with console_lock:
                if tui_ctx:
                    tui_ctx.refresh()
                else:
                    console.print(f"  [w{worker_id}] {scenario.id} × {persona.id} ...")

            run_start = time.time()
            # The attempt counter is per-process and per-run. A --resume redoes
            # a run in a new process, which starts it at attempt 1 with a fresh
            # budget and an empty prior_failures, so attempt_number means
            # "attempts in this process", never a lifetime total.
            #
            # The earlier process's history is dropped rather than merged, for a
            # different reason in each of the two resume cases. An interrupted
            # run never wrote a record.json, so its attempts are genuinely
            # unrecoverable. A system_error run did write one, and
            # _classify_resume_runs in cli.py reads it to decide the run needs
            # redoing at all — so that record's attempt_number and prior_failures
            # are in hand at that moment, and are deliberately discarded when the
            # redone run overwrites the file. Carrying them forward is deferred,
            # not impossible.
            #
            # Consequence worth knowing: a run that spent attempts, was
            # interrupted, then succeeded after a --resume reports attempt 1, so
            # the report's "retried" marker does not fire for it. Issue #346.
            max_attempts = 1 + (
                scenario.max_run_retries
                if scenario.max_run_retries is not None
                else run_max_retries
            )
            prior_failures: list[RunFailure] = []
            record: RunRecord | None = None

            for attempt in range(1, max_attempts + 1):
                # Every attempt at this run shares run_dir, so a retry used to
                # download into the previous attempt's artifacts/ — renamed to
                # "-N" by the API runner, overwritten by the browser runner.
                # Both derive that directory from run_dir at download time
                # rather than caching a handle, so moving it aside before the
                # runner exists is enough to give this attempt a clean one.
                # Keyed on the directory's contents, not on `attempt`, so a
                # resumed run (a new process, counter back at 1) is covered
                # too. Issue #346.
                quarantine_dest = quarantine_stale_artifacts(run_dir)
                if quarantine_dest is not None:
                    logger.info(
                        "[experiment] Previous artifacts moved to %s",
                        quarantine_dest.name,
                    )
                runner = await runner_factory.create(
                    run_dir, fixtures_dir, experiment_root
                )
                orchestrator: Orchestrator | None = None  # reset each attempt

                # Descriptions were resolved once per experiment before fan-out;
                # this only mints a fresh Artifact per attempt (clean at_turn/id)
                # from that map — no re-summarization here.
                fixture_artifacts = build_fixture_artifacts(
                    scenario.fixtures,
                    fixtures_dir,
                    experiment_root,
                    fixture_content_descriptions,
                )

                try:
                    run_config = RunConfig(
                        persona=persona.id,
                        scenario=scenario.id,
                        task_id=task_id,
                        trial_index=trial_index,
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
                        experiment_root=experiment_root,
                        fixture_artifacts=fixture_artifacts,
                        trial_index=trial_index,
                        state=state,
                        tui_ctx=tui_ctx,
                        shutdown_event=shutdown_event,
                    )
                    record = await orchestrator.run()
                    record.attempt_number = attempt
                    record.max_allowed_attempts = max_attempts
                    record.prior_failures = prior_failures
                    break
                except RunRecoverableError as exc:
                    partial = (
                        orchestrator.partial_record("system_error")
                        if orchestrator is not None
                        else None
                    )
                    turn_reached = (
                        partial.outcome.total_turns if partial is not None else 0
                    )
                    duration_ms = int((time.time() - run_start) * 1000)
                    failure = RunFailure(
                        attempt_number=attempt,
                        failure_type=type(exc).__name__,
                        submission_phase="unknown",
                        turn_reached=turn_reached,
                        error_message=str(exc) or type(exc).__name__,
                        duration_ms=duration_ms,
                    )
                    prior_failures.append(failure)
                    logger.warning(
                        "[experiment] Worker w%d: %s on attempt %d/%d for %s × %s: %s",
                        worker_id,
                        type(exc).__name__,
                        attempt,
                        max_attempts,
                        task_id,
                        persona.id,
                        exc,
                    )

                    if attempt == max_attempts:
                        if partial is not None:
                            record = partial
                            record.attempt_number = attempt
                            record.max_allowed_attempts = max_attempts
                            record.prior_failures = prior_failures
                        else:
                            record = RunRecord(
                                config=RunConfig(
                                    persona=persona.id,
                                    scenario=scenario.id,
                                    task_id=task_id,
                                    trial_index=trial_index,
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
                                artifacts=[],
                                attempt_number=attempt,
                                max_allowed_attempts=max_attempts,
                                prior_failures=prior_failures,
                            )
                    else:
                        await asyncio.sleep(run_retry_delay_seconds)
                        run_start = time.time()

                except Exception as exc:
                    # Unexpected crash. Capture the traceback (previously
                    # swallowed), preserve any turns the orchestrator
                    # completed, and retry within the configured budget.
                    partial = (
                        orchestrator.partial_record("system_error")
                        if orchestrator is not None
                        else None
                    )
                    turn_reached = (
                        partial.outcome.total_turns if partial is not None else 0
                    )
                    duration_ms = int((time.time() - run_start) * 1000)
                    logger.exception(
                        "[experiment] Worker w%d: unexpected crash on attempt "
                        "%d/%d for %s × %s (reached turn %d)",
                        worker_id,
                        attempt,
                        max_attempts,
                        task_id,
                        persona.id,
                        turn_reached,
                    )
                    prior_failures.append(
                        RunFailure(
                            attempt_number=attempt,
                            failure_type=type(exc).__name__,
                            submission_phase="unknown",
                            turn_reached=turn_reached,
                            # str(exc) is empty for message-less exceptions;
                            # fall back to the class name so it is never blank.
                            error_message=str(exc) or type(exc).__name__,
                            duration_ms=duration_ms,
                        )
                    )

                    if attempt == max_attempts:
                        record = (
                            partial
                            if partial is not None
                            else RunRecord(
                                config=RunConfig(
                                    persona=persona.id,
                                    scenario=scenario.id,
                                    task_id=task_id,
                                    trial_index=trial_index,
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
                                artifacts=[],
                            )
                        )
                        record.attempt_number = attempt
                        record.max_allowed_attempts = max_attempts
                        record.prior_failures = prior_failures
                        break

                    await asyncio.sleep(run_retry_delay_seconds)
                    run_start = time.time()

            assert record is not None  # always set: loop runs at least once

            # Emit post-run orchestration events
            if state:
                state.mark_run_completed(
                    task_id,
                    persona.id,
                    trial_index=trial_index,
                    stop_reason=record.outcome.stop_reason,
                    duration_seconds=record.outcome.duration_seconds,
                )
            if orchestration_logger:
                orchestration_logger.run_completed(
                    task_id,
                    persona.id,
                    trial_index=trial_index,
                    num_trials=scenario.num_trials,
                    stop_reason=record.outcome.stop_reason,
                    total_turns=record.outcome.total_turns,
                    duration_seconds=record.outcome.duration_seconds,
                )
            if log_router:
                log_router.close_run(task_id, persona.id, trial_index=trial_index)

            # Check scenario completion
            if (
                state
                and orchestration_logger
                and _scenario_just_completed(state, task_id)
            ):
                sc = next(s for s in state.scenarios if s.scenario_id == task_id)
                passed = sum(1 for r in sc.runs if r.stop_reason == "goal_achieved")
                orchestration_logger.scenario_completed(
                    task_id, runs_passed=passed, runs_total=len(sc.runs)
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

            if record.artifacts:
                manifest = _save_artifacts(record, run_dir, experiment_root)
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
    runs: list[RunPlanItem],
    concurrency: int,
) -> list[list[RunPlanItem]]:
    """Distribute runs across workers using round-robin."""
    slices: list[list[RunPlanItem]] = [[] for _ in range(concurrency)]
    for i, run in enumerate(runs):
        slices[i % concurrency].append(run)
    return slices


def _save_run_record(record: RunRecord, run_dir: Path) -> None:
    """Save a run record as record.json inside the run folder."""
    filepath = run_dir / "record.json"
    filepath.write_text(json.dumps(record.model_dump(), indent=2), encoding="utf-8")


def _scenario_just_completed(state: SimulationState, scenario_id: str) -> bool:
    """Return True when every run in the given scenario is now complete/failed."""
    sc = next((s for s in state.scenarios if s.scenario_id == scenario_id), None)
    return sc is not None and sc.phase == "completed"
