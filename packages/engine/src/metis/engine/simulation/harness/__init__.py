"""Python Playwright harness for target system simulation.

The auth flow, page selectors, and session-ID extraction are currently
coupled to Orca (the default target).
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from metis.core.console import console
from metis.core.logging import get_logger

from ..types import Experiment, ExperimentTask, Persona, RunRecord
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
) -> None:
    """Run a full experiment (all task x persona pairs).

    Manages: browser launch -> login -> iterate pairs -> save records -> close.
    Records are saved as runs/<task>-<persona>-<trial>/record.json inside output_dir.
    """
    # Expand tasks into individual runs
    runs: list[tuple[ExperimentTask, Persona, int]] = []
    for task in experiment.tasks:
        for persona_ref in task.persona_refs:
            persona = personas_by_id.get(persona_ref)
            if not persona:
                available = ", ".join(personas_by_id.keys())
                raise ValueError(
                    f"Task '{task.id}': unknown persona_ref '{persona_ref}'. Available: {available}"
                )
            for trial in range(task.num_trials):
                runs.append((task, persona, trial))

    total_runs = len(runs)

    logger.info("=" * 60)
    logger.info("[experiment] STARTING EXPERIMENT")
    logger.info("[experiment]   Total runs: %d", total_runs)
    logger.info("[experiment]   Output dir: %s", output_dir or "results/ (default)")
    logger.info("[experiment]   Mode: %s", "headed" if headed else "headless")
    logger.info("[experiment]   Tasks: %s", ", ".join(t.id for t in experiment.tasks))
    logger.info("[experiment]   Personas: %s", ", ".join(personas_by_id.keys()))
    logger.info("=" * 60)

    results: list[RunRecord] = []
    run_index = 0

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

            for task, persona, trial in runs:
                run_index += 1
                trial_label = (
                    f" (trial {trial + 1}/{task.num_trials})"
                    if task.num_trials > 1
                    else ""
                )
                logger.info("")
                logger.info("=" * 60)
                logger.info(
                    "[experiment] RUN [%d/%d]: %s x %s%s",
                    run_index,
                    total_runs,
                    persona.id,
                    task.id,
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
                pad = len(str(task.num_trials))
                run_folder_name = f"{task.id}-{persona.id}-{trial_index:0{pad}}"
                run_dir = (
                    (output_dir / "runs" / run_folder_name)
                    if output_dir
                    else Path("results") / "runs" / run_folder_name
                )
                run_dir.mkdir(parents=True, exist_ok=True)

                console.print(
                    f"  [{run_index}/{total_runs}] {task.id} × {persona.id} ..."
                )

                record = run_simulation(
                    page,
                    config,
                    persona,
                    task,
                    run_dir,
                    fixtures_dir,
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
                    f"  [{run_index}/{total_runs}] {task.id} × {persona.id} — "
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
                        "[experiment] Artifacts: %d saved (session: %s)",
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
        console.print(f"  [{status}] {r.config.persona} x {r.config.task}")
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
