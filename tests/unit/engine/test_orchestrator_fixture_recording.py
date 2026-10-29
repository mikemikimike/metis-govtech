"""The orchestrator records scenario fixtures as source='fixture' Artifacts (#321, #328)."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.core import Artifact
from metis.core.trials import TrialConfig
from metis.engine.simulation.gen_1.orchestrator import Orchestrator
from metis.engine.simulation.gen_1.runner import Runner
from metis.engine.simulation.gen_1.types import (
    ChosenAction,
    Observation,
    UserAgentOutput,
)
from metis.engine.simulation.types import Scenario


class _NoArtifactRunner(Runner):
    async def setup(self, config: TrialConfig) -> None:
        return None

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        return Observation(text="ok")

    async def teardown(self) -> None:
        pass

    async def get_session_id(self) -> str | None:
        return "sess-fx-1"


class _FakeAgent:
    async def generate_opening(self) -> UserAgentOutput:
        return UserAgentOutput(message="hello", decision="continue")

    async def generate_response(self, _payload: object) -> UserAgentOutput:
        return UserAgentOutput(message="done", decision="goal_achieved")


@pytest.mark.asyncio
async def test_fixtures_recorded_in_trial_record(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "input.csv").write_text("a,b\n1,2\n")

    orchestrator = Orchestrator(
        runner=_NoArtifactRunner(),
        agent=_FakeAgent(),  # type: ignore[arg-type]
        trial_config=TrialConfig(persona="p1", scenario="s1", fixtures=["input.csv"]),
        scenario=Scenario(id="s1", description="d", persona_refs=["p1"]),
        run_dir=tmp_path,
        fixtures_dir=fixtures_dir,
        experiment_root=tmp_path,
    )

    record = await orchestrator.execute()

    fixtures = [a for a in record.artifacts if a.source == "fixture"]
    assert [a.name for a in fixtures] == ["input.csv"]
    assert fixtures[0].path == "fixtures/input.csv"
    assert len(fixtures[0].digest or "") == 64


def test_orchestrator_uses_supplied_fixture_artifacts(tmp_path: Path) -> None:
    shared = [
        Artifact(name="q3.csv", source="fixture", path="q3.csv", state="received")
    ]
    orch = Orchestrator(
        runner=object(),  # unused in this assertion
        agent=object(),
        trial_config=TrialConfig(persona="p", scenario="s", fixtures=["q3.csv"]),
        scenario=Scenario(
            id="s", description="d", persona_refs=["p"], fixtures=["q3.csv"]
        ),
        run_dir=tmp_path,
        fixtures_dir=tmp_path,
        experiment_root=tmp_path,
        fixture_artifacts=shared,
    )
    assert orch._fixture_artifacts is shared
    assert orch._fixtures_by_name == {"q3.csv": shared[0]}
