"""The per-attempt seam between the retry loop and a simulator generation.

The runner factory's optional ``generation`` attribute picks the generation; a factory
without one is ``"gen_1"``. Each generation registers in ``_GENERATIONS`` what the
experiment needs from it: how to build an attempt's trial and how to describe the
fixtures. Retiring a generation means deleting its entry and its folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .gen_1.trial import build_trial as build_gen_1_trial
from .gen_1.trial import resolve_fixture_descriptions as gen_1_descriptions
from .gen_2.trial import build_trial as build_gen_2_trial
from .gen_2.trial import resolve_fixture_descriptions as gen_2_descriptions

if TYPE_CHECKING:
    import threading
    from collections.abc import Awaitable, Callable, Iterable
    from pathlib import Path

    from metis.core import Artifact
    from metis.core.trials import TrialConfig, TrialRecord
    from metis.engine.tui import SimulationState, TUIContext

    from .factory import RunnerFactory
    from .types import Persona, Scenario


class Trial(Protocol):
    """One attempt at a trial, as the experiment's retry loop drives it."""

    async def execute(self) -> TrialRecord:
        """Run the trial to completion and return its record."""
        ...

    def partial_record(self, stop_reason: str) -> TrialRecord:
        """Build a record from whatever progress the trial has made."""
        ...


@dataclass(frozen=True)
class SimulatorGeneration:
    """What the experiment needs from one simulator generation."""

    build_trial: Callable[..., Trial]
    """Build one attempt's trial around a runner (the keyword arguments of ``create_trial``)."""
    resolve_fixture_descriptions: Callable[
        [Iterable[str], Path, Path, dict[str, str]], Awaitable[dict[str, str]]
    ]
    """Resolve one description per fixture, once per experiment, before workers start."""


_GENERATIONS: dict[str, SimulatorGeneration] = {
    "gen_1": SimulatorGeneration(
        build_trial=build_gen_1_trial,
        resolve_fixture_descriptions=gen_1_descriptions,
    ),
    "gen_2": SimulatorGeneration(
        build_trial=build_gen_2_trial,
        resolve_fixture_descriptions=gen_2_descriptions,
    ),
}


def resolve_generation(runner_factory: RunnerFactory) -> SimulatorGeneration:
    """Return the generation ``runner_factory``'s runners belong to.

    Raises:
        ValueError: If the factory names a generation that is not registered.
    """
    name = getattr(type(runner_factory), "generation", "gen_1")
    if name not in _GENERATIONS:
        supported = ", ".join(repr(g) for g in sorted(_GENERATIONS))
        raise ValueError(
            f"Unsupported simulator generation {name!r} on "
            f"{type(runner_factory).__name__}; supported: {supported}"
        )
    return _GENERATIONS[name]


def create_trial(
    runner_factory: RunnerFactory,
    *,
    generation: SimulatorGeneration | None = None,
    runner: object,
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
    """Return the trial for ``runner_factory``'s generation, built around ``runner``.

    The experiment passes the ``generation`` it already resolved; without one, it is
    looked up from the factory.
    """
    generation = generation or resolve_generation(runner_factory)
    return generation.build_trial(
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
