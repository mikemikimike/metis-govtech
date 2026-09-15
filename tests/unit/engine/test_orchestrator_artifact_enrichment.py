"""Orchestrator enriches downloaded artifacts before recording the turn (#307)."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.engine.simulation import orchestrator as orch_module
from metis.engine.simulation.orchestrator import Orchestrator
from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
    Artifact,
    ChosenAction,
    Observation,
    RunConfig,
    Scenario,
    UserAgentOutput,
)


class _FakeRunner(Runner):
    """Returns one download artifact on the first (and only) turn."""

    def __init__(self, artifact: Artifact) -> None:
        self._artifact = artifact

    async def setup(self, config: RunConfig) -> None:
        return None

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        return Observation(text="here is your file", artifacts=[self._artifact])

    async def teardown(self) -> None:
        pass

    async def get_session_id(self) -> str | None:
        return "sess-enrich-1"


class _FakeAgent:
    """Opening: continue (drives turn 1). Response: goal_achieved (stops loop)."""

    async def generate_opening(self) -> UserAgentOutput:
        return UserAgentOutput(message="please give me a file", decision="continue")

    async def generate_response(self, _payload: object) -> UserAgentOutput:
        return UserAgentOutput(message="got it, done", decision="goal_achieved")


def _scenario() -> Scenario:
    return Scenario(
        id="s1",
        description="a scenario",
        persona_refs=["p1"],
        max_turns=20,
    )


@pytest.mark.asyncio
async def test_orchestrator_summarizes_downloads(monkeypatch, tmp_path: Path) -> None:
    seen: list[tuple[str, int]] = []

    async def _fake_summarize(artifact, *, triggering_message, turn_number):
        seen.append((triggering_message, turn_number))
        artifact.content_description = "3 rows x 2 cols"
        artifact.state_description = f"delivered at turn {turn_number}"

    monkeypatch.setattr(orch_module, "summarize_artifact", _fake_summarize)

    # Create a real file so the URI points to something on disk
    csv_file = tmp_path / "x.csv"
    csv_file.write_text("col1,col2\n1,2\n3,4\n5,6\n")
    uri = csv_file.as_uri()

    artifact = Artifact(name="x.csv", type="download", uri=uri)
    runner = _FakeRunner(artifact)
    scenario = _scenario()
    run_config = RunConfig(persona="p1", scenario="s1")
    orchestrator = Orchestrator(
        runner=runner,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        run_config=run_config,
        scenario=scenario,
        run_dir=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
    )

    record = await orchestrator.run()

    assert seen and seen[0][1] == 1
    art = record.artifacts_collected[0]
    assert art.content_description == "3 rows x 2 cols"
    assert art.collected_at_turn == 1
