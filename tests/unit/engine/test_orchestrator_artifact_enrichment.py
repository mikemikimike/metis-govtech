"""Orchestrator enriches downloaded artifacts before recording the turn (#307, #328)."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation.gen_1 import orchestrator as orch_module
from metis.engine.simulation.gen_1.orchestrator import Orchestrator
from metis.engine.simulation.gen_1.runner import Runner
from metis.engine.simulation.gen_1.types import (
    ChosenAction,
    Observation,
    UserAgentOutput,
)
from metis.engine.simulation.types import Artifact, Scenario


class _FakeRunner(Runner):
    """Returns one download artifact on the first (and only) turn."""

    def __init__(self, artifact: Artifact) -> None:
        self._artifact = artifact

    async def setup(self, config: TrialConfig) -> None:
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

    async def _fake_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log, **_
    ):
        seen.append((triggering_message, turn_number))
        artifact.content_description = "3 rows x 2 cols"
        artifact.state_description = f"delivered at turn {turn_number}"

    monkeypatch.setattr(orch_module, "summarize_artifact", _fake_summarize)

    # Create a real file so the path points to something on disk
    csv_file = tmp_path / "x.csv"
    csv_file.write_text("col1,col2\n1,2\n3,4\n5,6\n")

    artifact = Artifact(name="x.csv", path="x.csv", state="received")
    runner = _FakeRunner(artifact)
    scenario = _scenario()
    trial_config = TrialConfig(persona="p1", scenario="s1")
    orchestrator = Orchestrator(
        runner=runner,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        trial_config=trial_config,
        scenario=scenario,
        run_dir=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
        experiment_root=tmp_path,
    )

    record = await orchestrator.execute()

    assert seen and seen[0][1] == 1
    art = record.artifacts[0]
    assert art.content_description == "3 rows x 2 cols"
    assert art.at_simulated_turn == 1


@pytest.mark.asyncio
async def test_fixture_stub_swapped_for_registry_object_and_deduped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from metis.engine.simulation.gen_1 import orchestrator as orch_mod

    # The worker-enriched registry object (has a description; no at_simulated_turn yet).
    registry = Artifact(
        name="q3.csv",
        source="fixture",
        path="q3.csv",
        content_description="Q3 sales, 200 rows.",
        state="received",
    )
    orch = Orchestrator(
        runner=object(),
        agent=object(),
        trial_config=TrialConfig(persona="p", scenario="s", fixtures=["q3.csv"]),
        scenario=Scenario(
            id="s", description="d", persona_refs=["p"], fixtures=["q3.csv"]
        ),
        run_dir=tmp_path,
        fixtures_dir=tmp_path,
        experiment_root=tmp_path,
        fixture_artifacts=[registry],
    )

    # summarize_artifact must NOT be called for a fixture.
    calls: list[str] = []

    async def spy_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log, **_
    ):
        calls.append(artifact.name)

    monkeypatch.setattr(orch_mod, "summarize_artifact", spy_summarize)

    # The runner emitted a DIFFERENT object (fresh id) with the same name.
    stub = Artifact(name="q3.csv", source="fixture", path="q3.csv", state="received")
    assert stub.id != registry.id
    obs = Observation(text="ok", artifacts=[stub])

    await orch._enrich_observation_artifacts(obs, turn_count=3, current_message="here")

    # Stub replaced in place by the registry object; at_simulated_turn stamped; not summarized.
    assert obs.artifacts[0] is registry
    assert registry.at_simulated_turn == 3
    assert calls == []  # fixtures skip summarize

    # Record dedups: registry appears in both _fixture_artifacts and collected.
    record = orch._build_record("goal_achieved", list(obs.artifacts), 0.0, None)
    ids = [a.id for a in record.artifacts]
    assert ids.count(registry.id) == 1
    assert record.artifacts[0].content_description == "Q3 sales, 200 rows."


@pytest.mark.asyncio
async def test_target_artifact_still_stamped_and_summarized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from metis.engine.simulation.gen_1 import orchestrator as orch_mod

    orch = Orchestrator(
        runner=object(),
        agent=object(),
        trial_config=TrialConfig(persona="p", scenario="s"),
        scenario=Scenario(id="s", description="d", persona_refs=["p"]),
        run_dir=tmp_path,
        fixtures_dir=tmp_path,
        experiment_root=tmp_path,
        fixture_artifacts=[],
    )
    calls: list[str] = []

    async def spy_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log, **_
    ):
        calls.append(artifact.name)

    monkeypatch.setattr(orch_mod, "summarize_artifact", spy_summarize)

    target = Artifact(name="out.csv", source="target", path="out.csv", state="received")
    obs = Observation(text="ok", artifacts=[target])
    await orch._enrich_observation_artifacts(obs, turn_count=2, current_message="go")

    assert target.at_simulated_turn == 2
    assert calls == ["out.csv"]  # targets are summarized


def _fixture_swap_orchestrator(tmp_path: Path, registry: Artifact) -> Orchestrator:
    return Orchestrator(
        runner=object(),
        agent=object(),
        trial_config=TrialConfig(persona="p", scenario="s", fixtures=[registry.name]),
        scenario=Scenario(
            id="s", description="d", persona_refs=["p"], fixtures=[registry.name]
        ),
        run_dir=tmp_path,
        fixtures_dir=tmp_path,
        experiment_root=tmp_path,
        fixture_artifacts=[registry],
    )


@pytest.mark.asyncio
async def test_fixture_external_id_survives_the_registry_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stub is the only object that can know the target's file id (#337).

    The registry object is built at staging time, before a session exists, so
    without carrying the field across the swap every fixture reaches
    ``record.json`` and ``run-manifest.json`` with ``external_id: null`` no
    matter what the runner stamped.
    """
    registry = Artifact(
        name="q3.csv",
        source="fixture",
        path="q3.csv",
        content_description="Q3 sales, 200 rows.",
        state="received",
    )
    assert registry.external_id is None
    orch = _fixture_swap_orchestrator(tmp_path, registry)

    async def spy_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log, **_
    ):
        raise AssertionError("fixtures must not be summarized")

    monkeypatch.setattr(orch_module, "summarize_artifact", spy_summarize)

    stub = Artifact(
        name="q3.csv",
        source="fixture",
        path="q3.csv",
        external_id="orca-file-77",
        state="received",
    )
    obs = Observation(text="ok", artifacts=[stub])
    await orch._enrich_observation_artifacts(obs, turn_count=1, current_message="here")

    assert obs.artifacts[0] is registry
    assert registry.external_id == "orca-file-77"

    # The field has to reach the record, which is the whole point of stamping it.
    record = orch._build_record("goal_achieved", list(obs.artifacts), 0.0, None)
    assert [a.external_id for a in record.artifacts] == ["orca-file-77"]


@pytest.mark.asyncio
async def test_a_later_echo_without_an_id_does_not_blank_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The carry is guarded, so the copy cannot lose an established id."""
    registry = Artifact(
        name="q3.csv", source="fixture", path="q3.csv", state="received"
    )
    orch = _fixture_swap_orchestrator(tmp_path, registry)

    async def spy_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log, **_
    ):
        raise AssertionError("fixtures must not be summarized")

    monkeypatch.setattr(orch_module, "summarize_artifact", spy_summarize)

    with_id = Artifact(
        name="q3.csv",
        source="fixture",
        path="q3.csv",
        external_id="orca-file-77",
        state="received",
    )
    await orch._enrich_observation_artifacts(
        Observation(text="ok", artifacts=[with_id]), turn_count=1, current_message="a"
    )
    assert registry.external_id == "orca-file-77"

    without_id = Artifact(
        name="q3.csv", source="fixture", path="q3.csv", state="received"
    )
    await orch._enrich_observation_artifacts(
        Observation(text="ok", artifacts=[without_id]),
        turn_count=2,
        current_message="b",
    )
    assert registry.external_id == "orca-file-77"
    assert registry.at_simulated_turn == 2
