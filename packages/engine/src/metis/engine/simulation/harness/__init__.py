"""Python Playwright harness for target system simulation.

The auth flow, page selectors, and session-ID extraction are currently
coupled to Orca (the default target).
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from metis.core.console import console
from metis.core.logging import get_logger
from metis.engine.logging import LogRouter, OrchestrationLogger
from metis.engine.tui import SimulationState, TUIContext

from ..types import Experiment, Persona, RunRecord, Scenario
from ._artifact_store import _save_artifacts
from ._auth import login
from ._config import HarnessConfig
from ._environment import run_simulation

__all__ = ["HarnessConfig", "run_experiment", "run_simulation"]

logger = get_logger()


def run_experiment(
    config: HarnessConfig,
    experiment: Experiment,
    personas_by_id: dict[str, Persona],
    fixtures_dir: Path,
    output_dir: Path | None = None,
    headed: bool = False,
    # Optional hooks for TUI / structured-logging integration
    state: SimulationState | None = None,
    orchestration_logger: OrchestrationLogger | None = None,
    log_router: LogRouter | None = None,
    tui_ctx: TUIContext | None = None,
) -> None:
    """Run a full experiment (all scenario x persona pairs).

    Manages: browser launch -> login -> iterate pairs -> save records -> close.
    Records are saved as runs/<scenario>-<persona>-<trial>/record.json inside output_dir.
    """
    # Expand scenarios into individual runs
    runs: list[tuple[Scenario, Persona, int]] = []
    for scenario in experiment.scenarios:
        for persona_ref in scenario.persona_refs:
            persona = personas_by_id.get(persona_ref)
            if not persona:
                available = ", ".join(personas_by_id.keys())
                raise ValueError(
                    f"Scenario '{scenario.id}': unknown persona_ref '{persona_ref}'. Available: {available}"
                )
            for trial in range(scenario.num_trials):
                runs.append((scenario, persona, trial))

    total_runs = len(runs)

    logger.info("=" * 60)
    logger.info("[experiment] STARTING EXPERIMENT")
    logger.info("[experiment]   Total runs: %d", total_runs)
    logger.info("[experiment]   Output dir: %s", output_dir or "results/ (default)")
    logger.info("[experiment]   Mode: %s", "headed" if headed else "headless")
    logger.info(
        "[experiment]   Scenarios: %s", ", ".join(s.id for s in experiment.scenarios)
    )
    logger.info("[experiment]   Personas: %s", ", ".join(personas_by_id.keys()))
    logger.info("=" * 60)

    results: list[RunRecord] = []
    run_index = 0
    prev_scenario: Scenario | None = None

    with sync_playwright() as pw:
        logger.info(
            "[experiment] Launching Chromium browser (%s mode)...",
            "headed" if headed else "headless",
        )
        browser = pw.chromium.launch(headless=not headed)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                accept_downloads=True,
            )
            page = context.new_page()
            logger.info("[experiment] Browser ready (viewport: 1440x900)")

            # Login once
            logger.info("[experiment] Starting login sequence...")
            login(page, config)

            for scenario, persona, trial in runs:
                run_index += 1
                trial_label = (
                    f" (trial {trial + 1}/{scenario.num_trials})"
                    if scenario.num_trials > 1
                    else ""
                )
                logger.info("")
                logger.info("=" * 60)
                logger.info(
                    "[experiment] RUN [%d/%d]: %s x %s%s",
                    run_index,
                    total_runs,
                    persona.id,
                    scenario.id,
                    trial_label,
                )
                logger.info("=" * 60)

                # Start a fresh chat (except first run — login already did it)
                if run_index > 1:
                    logger.info("[experiment] Starting fresh chat...")
                    try:
                        page.get_by_text("New chat").click(timeout=5000)
                        page.wait_for_timeout(2000)
                        logger.info("[experiment] Clicked 'New chat'")
                    except Exception:
                        logger.info(
                            "[experiment] 'New chat' not found — navigating to /chat"
                        )
                        page.goto(
                            config.url + "/chat",
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                        page.wait_for_timeout(2000)
                    # Dismiss tour modal if it reappears
                    try:
                        skip_btn = page.get_by_text("Skip for now")
                        if skip_btn.is_visible(timeout=2000):
                            logger.info("[experiment] Dismissing tour modal")
                            skip_btn.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        pass

                trial_index = trial + 1
                pad = len(str(scenario.num_trials))
                run_folder_name = f"{scenario.id}-{persona.id}-{trial_index:0{pad}}"
                run_dir = (
                    (output_dir / "runs" / run_folder_name)
                    if output_dir
                    else Path("results") / "runs" / run_folder_name
                )
                run_dir.mkdir(parents=True, exist_ok=True)

                # --- Bind structlog context for this run ---
                import structlog.contextvars

                structlog.contextvars.clear_contextvars()
                structlog.contextvars.bind_contextvars(
                    scenario_id=scenario.id,
                    persona_id=persona.id,
                    trial=trial_index,
                )

                # --- Emit pre-run orchestration events ---
                if _is_new_scenario(scenario, prev_scenario) and orchestration_logger:
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
                    state.start_run(scenario.id, persona.id, trial=trial_index)
                if tui_ctx:
                    tui_ctx.refresh()

                prev_scenario = scenario

                console.print(
                    f"  [{run_index}/{total_runs}] {scenario.id} × {persona.id} ..."
                )

                record = run_simulation(
                    page,
                    config,
                    persona,
                    scenario,
                    run_dir,
                    fixtures_dir,
                    trial=trial_index,
                    state=state,
                    tui_ctx=tui_ctx,
                )

                # --- Emit post-run orchestration events ---
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
                if tui_ctx:
                    tui_ctx.refresh()

                # Emit scenario completion when all runs for this scenario are done
                if state and _scenario_just_completed(state, scenario.id):
                    sc = next(
                        s for s in state.scenarios if s.scenario_id == scenario.id
                    )
                    passed = sum(1 for r in sc.runs if r.stop_reason == "goal_achieved")
                    if orchestration_logger:
                        orchestration_logger.scenario_completed(
                            scenario.id, runs_passed=passed, runs_total=len(sc.runs)
                        )

                # Save run record to disk
                _save_run_record(record, run_dir)
                logger.info("[experiment] Saved record: %s", run_dir / "record.json")

                # Build per-turn timing breakdown
                timing_parts: list[str] = []
                for t in record.conversation:
                    timing_parts.append(f"t{t.turn_number}={t.duration_ms / 1000:.0f}s")
                timing_str = f" [{', '.join(timing_parts)}]" if timing_parts else ""

                console.print(
                    f"  [{run_index}/{total_runs}] {scenario.id} × {persona.id} — "
                    f"{record.outcome.stop_reason}, {record.outcome.total_turns} turns, "
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

                results.append(record)
        finally:
            logger.info("[experiment] Closing browser...")
            browser.close()

    console.print("\n\n========== SIMULATION SUMMARY ==========\n")
    for r in results:
        status = "PASS" if r.outcome.stop_reason == "goal_achieved" else "----"
        console.print(f"  [{status}] {r.config.persona} x {r.config.scenario}")
        console.print(
            f"         Turns: {r.outcome.total_turns}, "
            f"Duration: {r.outcome.duration_seconds}s, "
            f"Reason: {r.outcome.stop_reason}"
        )
    console.print()
    achieved = sum(1 for r in results if r.outcome.stop_reason == "goal_achieved")
    console.print(f"Goals achieved: {achieved}/{len(results)}")


def _save_run_record(record: RunRecord, run_dir: Path) -> None:
    """Save a run record as record.json inside the run folder."""
    filepath = run_dir / "record.json"
    filepath.write_text(json.dumps(record.model_dump(), indent=2))


def _is_new_scenario(current: Scenario, prev: Scenario | None) -> bool:
    """Return True when we are entering a new scenario (first run or ID changed)."""
    return prev is None or current.id != prev.id


def _scenario_just_completed(state: SimulationState, scenario_id: str) -> bool:
    """Return True when every run in the given scenario is now complete/failed."""
    sc = next((s for s in state.scenarios if s.scenario_id == scenario_id), None)
    return sc is not None and sc.phase == "completed"
