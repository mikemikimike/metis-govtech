"""The "run one trial" seam: the runner factory picks the simulator generation (#475)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation.experiment import TrialPlanItem, _worker
from metis.engine.simulation.gen_1 import trial as gen_1_trial
from metis.engine.simulation.trial import create_trial
from metis.engine.simulation.types import Persona, Scenario


class _Factory:
    """Factory that hands out mock runners and counts how many it made."""

    def __init__(self) -> None:
        self.created = 0

    async def start(self) -> None:
        pass

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> Any:
        self.created += 1
        return AsyncMock()

    async def close(self) -> None:
        pass


@pytest.fixture
def scenario() -> Scenario:
    return Scenario(
        id="test-scenario",
        description="A simple test scenario",
        persona_refs=["tester"],
        num_trials=1,
        max_turns=1,
        grader_refs=[],
    )


@pytest.fixture
def persona() -> Persona:
    return Persona(id="tester", description="A test persona")


def _trial_kwargs(
    persona: Persona, scenario: Scenario, tmp_path: Path
) -> dict[str, Any]:
    return {
        "runner": "runner",
        "persona": persona,
        "scenario": scenario,
        "trial_config": TrialConfig(persona="tester", scenario="test-scenario"),
        "run_dir": tmp_path,
        "fixtures_dir": tmp_path,
        "experiment_root": tmp_path,
        "fixture_artifacts": [],
        "trial_index": 1,
        "state": None,
        "tui_ctx": None,
        "shutdown_event": None,
    }


async def _run_worker(
    factory: _Factory,
    persona: Persona,
    scenario: Scenario,
    tmp_path: Path,
    *,
    trial_max_retries: int,
) -> list[Any]:
    return await _worker(
        worker_id=0,
        runner_factory=factory,
        worker_trials=[TrialPlanItem(scenario, persona, 1)],
        experiment_root=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
        fixture_content_descriptions={},
        console_lock=asyncio.Lock(),
        started_scenarios=set(),
        trial_max_retries=trial_max_retries,
        trial_retry_delay_seconds=0,
    )


def test_factory_without_generation_gets_gen_1_trial(
    monkeypatch: pytest.MonkeyPatch,
    persona: Persona,
    scenario: Scenario,
    tmp_path: Path,
) -> None:
    built: dict[str, dict[str, Any]] = {}

    def fake_agent(**kwargs: Any) -> str:
        built["agent"] = kwargs
        return "agent"

    def fake_orchestrator(**kwargs: Any) -> str:
        built["orch"] = kwargs
        return "orch"

    monkeypatch.setattr(gen_1_trial, "UserAgent", fake_agent)
    monkeypatch.setattr(gen_1_trial, "Orchestrator", fake_orchestrator)

    trial = create_trial(_Factory(), **_trial_kwargs(persona, scenario, tmp_path))

    assert trial == "orch"
    assert built["agent"] == {"persona": persona, "scenario": scenario}
    assert set(built["orch"]) == {
        "runner",
        "agent",
        "trial_config",
        "scenario",
        "run_dir",
        "fixtures_dir",
        "experiment_root",
        "fixture_artifacts",
        "trial_index",
        "state",
        "tui_ctx",
        "shutdown_event",
    }
    assert built["orch"]["agent"] == "agent"
    assert built["orch"]["runner"] == "runner"


def test_unknown_generation_raises(
    persona: Persona, scenario: Scenario, tmp_path: Path
) -> None:
    class _Gen2Factory(_Factory):
        generation = "gen_2"

    with pytest.raises(ValueError, match=r"'gen_2'.*supported: 'gen_1'"):
        create_trial(_Gen2Factory(), **_trial_kwargs(persona, scenario, tmp_path))


def test_generation_is_read_from_the_factory_class(
    monkeypatch: pytest.MonkeyPatch,
    persona: Persona,
    scenario: Scenario,
    tmp_path: Path,
) -> None:
    # A mock factory answers any attribute name; the seam must not mistake that
    # answer for a declared generation.
    monkeypatch.setattr(gen_1_trial, "UserAgent", lambda **_kw: "agent")
    monkeypatch.setattr(gen_1_trial, "Orchestrator", lambda **_kw: "orch")

    assert (
        create_trial(AsyncMock(), **_trial_kwargs(persona, scenario, tmp_path))
        == "orch"
    )


@pytest.mark.asyncio
async def test_worker_create_failure_propagates(
    persona: Persona, scenario: Scenario, tmp_path: Path
) -> None:
    factory = _Factory()
    factory.create = AsyncMock(side_effect=RuntimeError("no browser"))  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="no browser"):
        await _run_worker(factory, persona, scenario, tmp_path, trial_max_retries=2)

    assert factory.create.await_count == 1


@pytest.mark.asyncio
async def test_trial_construction_failure_retries_with_empty_record(
    monkeypatch: pytest.MonkeyPatch,
    persona: Persona,
    scenario: Scenario,
    tmp_path: Path,
) -> None:
    def boom(**_kwargs: Any) -> None:
        raise RuntimeError("bad persona")

    monkeypatch.setattr(gen_1_trial, "UserAgent", boom)
    factory = _Factory()

    [record] = await _run_worker(
        factory, persona, scenario, tmp_path, trial_max_retries=1
    )

    assert factory.created == 2
    assert record.outcome.stop_reason == "system_error"
    assert record.outcome.total_turns == 0
    assert record.attempt_number == 2
    assert record.max_allowed_attempts == 2
    assert [f.failure_type for f in record.prior_failures] == [
        "RuntimeError",
        "RuntimeError",
    ]
    assert record.prior_failures[0].error_message == "bad persona"
