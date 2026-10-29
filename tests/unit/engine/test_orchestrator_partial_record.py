"""Tests for Orchestrator.partial_record — preserving in-progress trial state."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation.gen_1.orchestrator import Orchestrator
from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
    ChosenAction,
    Observation,
    Scenario,
    UserAgentOutput,
)


class _FakeRunner(Runner):
    """Answers turn 1, then raises a message-less error on turn 2."""

    def __init__(self) -> None:
        self.calls = 0
        self.teardown_called = False

    async def setup(self, config: TrialConfig) -> None:
        return None

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        self.calls += 1
        if self.calls == 1:
            return Observation(text="first answer")
        raise RuntimeError()  # message-less, like the real crash

    async def teardown(self) -> None:
        self.teardown_called = True

    async def get_session_id(self) -> str | None:
        return "sess-fake-1"


class _FakeAgent:
    """Minimal UserAgent stand-in: canned opening + follow-up, no LLM."""

    async def generate_opening(self) -> UserAgentOutput:
        return UserAgentOutput(message="hello", decision="continue")

    async def generate_response(self, _payload: object) -> UserAgentOutput:
        return UserAgentOutput(message="keep going", decision="continue")


def _scenario() -> Scenario:
    return Scenario(
        id="s1",
        description="a scenario",
        persona_refs=["p1"],
        max_turns=20,
    )


@pytest.mark.asyncio
async def test_partial_record_preserves_completed_turns(tmp_path: Path) -> None:
    runner = _FakeRunner()
    scenario = _scenario()
    trial_config = TrialConfig(persona="p1", scenario="s1")
    orch = Orchestrator(
        runner=runner,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        trial_config=trial_config,
        scenario=scenario,
        run_dir=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
        experiment_root=tmp_path,
    )

    # Turn 2's send_turn raises; the exception escapes execute().
    with pytest.raises(RuntimeError):
        await orch.execute()

    record = orch.partial_record("system_error")

    assert record.outcome.stop_reason == "system_error"
    assert (
        record.outcome.simulated_turns_completed == 1
    )  # turn 1 completed, turn 2 crashed
    assert record.target_session_id == "sess-fake-1"
    assert runner.teardown_called is True  # finally: teardown still ran


def test_partial_record_callable_without_run(tmp_path: Path) -> None:
    """Verify partial_record() works even when execute() was never called."""
    runner = _FakeRunner()
    scenario = _scenario()
    trial_config = TrialConfig(persona="p1", scenario="s1")
    orch = Orchestrator(
        runner=runner,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        trial_config=trial_config,
        scenario=scenario,
        run_dir=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
        experiment_root=tmp_path,
    )

    # Do NOT call execute(); call partial_record() directly.
    record = orch.partial_record("system_error")

    assert record.outcome.stop_reason == "system_error"
    assert record.outcome.simulated_turns_completed == 0
