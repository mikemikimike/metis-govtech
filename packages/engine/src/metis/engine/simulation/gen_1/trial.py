"""gen_1's trial: today's user agent and orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .orchestrator import Orchestrator
from .user_agent.agent import UserAgent

if TYPE_CHECKING:
    import threading
    from pathlib import Path

    from metis.core import Artifact
    from metis.core.trials import TrialConfig
    from metis.engine.tui import SimulationState, TUIContext

    from ..types import Persona, Scenario
    from .runner import Runner


def build_trial(
    *,
    runner: Runner,
    persona: Persona,
    scenario: Scenario,
    trial_config: TrialConfig,
    run_dir: Path,
    fixtures_dir: Path,
    experiment_root: Path,
    fixture_artifacts: list[Artifact],
    trial_index: int,
    state: SimulationState | None,
    tui_ctx: TUIContext | None,
    shutdown_event: threading.Event | None,
) -> Orchestrator:
    """Build the user agent and the orchestrator that drives ``runner`` for one attempt."""
    agent = UserAgent(persona=persona, scenario=scenario)
    return Orchestrator(
        runner=runner,
        agent=agent,
        trial_config=trial_config,
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
