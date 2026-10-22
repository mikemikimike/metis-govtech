"""gen_2's trial: its user agent and orchestrator, and fixture facts written by code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._fixture_artifacts import build_fixture_artifacts
from ..artifacts import file_facts
from ..llm_calls import LLMCallLog
from .orchestrator import Orchestrator
from .user_agent.agent import UserAgent

if TYPE_CHECKING:
    import threading
    from collections.abc import Iterable
    from pathlib import Path

    from metis.core import Artifact
    from metis.core.trials import TrialConfig
    from metis.engine.tui import SimulationState, TUIContext

    from ..types import Persona, Scenario
    from .runner import Runner

__all__ = ["build_trial", "resolve_fixture_descriptions"]


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
    """Build the user agent and the orchestrator that drives ``runner`` for one attempt.

    ``fixtures_dir`` is part of the seam's signature but unused here: the fixtures arrive
    as ``fixture_artifacts``, already located.
    """
    del fixtures_dir
    agent = UserAgent(
        persona=persona, scenario=scenario, llm_log=LLMCallLog.for_trial(run_dir)
    )
    return Orchestrator(
        runner=runner,
        agent=agent,
        trial_config=trial_config,
        scenario=scenario,
        run_dir=run_dir,
        experiment_root=experiment_root,
        fixture_artifacts=fixture_artifacts,
        trial_index=trial_index,
        state=state,
        tui_ctx=tui_ctx,
        shutdown_event=shutdown_event,
    )


async def resolve_fixture_descriptions(
    fixture_names: Iterable[str],
    fixtures_dir: Path,
    experiment_root: Path,
    author_descriptions: dict[str, str],
) -> dict[str, str]:
    """One description per distinct fixture: the author's, else its file facts.

    No LLM is called. A fixture missing on disk is left out, as in gen_1.
    """
    artifacts = build_fixture_artifacts(
        sorted(set(fixture_names)), fixtures_dir, experiment_root, author_descriptions
    )
    root = experiment_root.resolve()
    return {
        a.name: a.content_description or file_facts(root / str(a.path), a.name)
        for a in artifacts
    }
