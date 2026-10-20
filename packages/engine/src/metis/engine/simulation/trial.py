"""The per-attempt seam between the retry loop and a simulator generation.

The runner factory's optional ``generation`` attribute picks the generation; a factory
without one is ``"gen_1"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .gen_1.trial import build_trial

if TYPE_CHECKING:
    import threading
    from pathlib import Path

    from metis.core import Artifact
    from metis.core.trials import TrialConfig, TrialRecord
    from metis.engine.tui import SimulationState, TUIContext

    from .factory import RunnerFactory
    from .gen_1.runner import Runner
    from .types import Persona, Scenario


class Trial(Protocol):
    """One attempt at a trial, as the experiment's retry loop drives it."""

    async def execute(self) -> TrialRecord:
        """Run the trial to completion and return its record."""
        ...

    def partial_record(self, stop_reason: str) -> TrialRecord:
        """Build a record from whatever progress the trial has made."""
        ...


def create_trial(
    runner_factory: RunnerFactory,
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
) -> Trial:
    """Return the trial for ``runner_factory``'s generation, built around ``runner``."""
    generation = getattr(type(runner_factory), "generation", "gen_1")
    if generation != "gen_1":
        raise ValueError(
            f"Unsupported simulator generation {generation!r} on "
            f"{type(runner_factory).__name__}; supported: 'gen_1'"
        )
    return build_trial(
        runner=runner,
        persona=persona,
        scenario=scenario,
        trial_config=trial_config,
        run_dir=run_dir,
        fixtures_dir=fixtures_dir,
        experiment_root=experiment_root,
        fixture_artifacts=fixture_artifacts,
        trial_index=trial_index,
        state=state,
        tui_ctx=tui_ctx,
        shutdown_event=shutdown_event,
    )
