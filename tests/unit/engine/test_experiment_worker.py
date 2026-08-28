"""Tests for _worker using a mock RunnerFactory."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from metis.engine.simulation.experiment import _worker, run_folder_name
from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
    ChosenAction,
    Observation,
    Persona,
    RunConfig,
    RunOutcome,
    RunRecord,
    Scenario,
)


class MockRunner(Runner):
    """Runner that completes immediately with a canned response."""

    def __init__(self) -> None:
        self.setup_called = False
        self.teardown_called = False

    async def setup(self, config: RunConfig) -> None:
        self.setup_called = True

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        return Observation(
            text="Goal achieved",
            artifacts=[],
            errors=[],
            available_actions=[],
            status_labels=["completed"],
        )

    async def teardown(self) -> None:
        self.teardown_called = True

    async def get_session_id(self) -> str | None:
        return "sess-mock-123"


class MockRunnerFactory:
    """Factory that returns MockRunners without needing Playwright."""

    def __init__(self) -> None:
        self.started = False
        self.runners_created: list[MockRunner] = []

    async def start(self) -> None:
        self.started = True

    async def create(self, run_dir: Path, fixtures_dir: Path) -> Runner:
        runner = MockRunner()
        self.runners_created.append(runner)
        return runner

    async def close(self) -> None:
        pass


@pytest.fixture
def simple_scenario() -> Scenario:
    return Scenario(
        id="test-scenario",
        description="A simple test scenario",
        persona_refs=["tester"],
        num_trials=1,
        max_turns=1,
        metric_refs=[],
    )


@pytest.fixture
def simple_persona() -> Persona:
    return Persona(id="tester", description="A test persona")


def _make_canned_record(scenario: Scenario, persona: Persona) -> RunRecord:
    """Create a canned RunRecord that the mocked orchestrator returns."""
    return RunRecord(
        config=RunConfig(
            persona=persona.id,
            scenario=scenario.id,
            metric_refs=[],
            max_turns=1,
        ),
        target_session_id="sess-mock-123",
        outcome=RunOutcome(
            stop_reason="goal_achieved",
            total_turns=1,
            duration_seconds=0.1,
        ),
        conversation=[],
        artifacts_collected=[],
    )


class TestWorkerWithMockFactory:
    @pytest.mark.asyncio
    async def test_worker_uses_factory_create(
        self, simple_scenario: Scenario, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """_worker calls runner_factory.create() and produces a RunRecord."""
        factory = MockRunnerFactory()
        await factory.start()

        run_slice = [(simple_scenario, simple_persona, 0)]
        console_lock = asyncio.Lock()

        canned = _make_canned_record(simple_scenario, simple_persona)

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            mock_orch_instance = AsyncMock()
            mock_orch_instance.run = AsyncMock(return_value=canned)
            mock_orch_cls.return_value = mock_orch_instance

            records = await _worker(
                worker_id=0,
                runner_factory=factory,
                run_slice=run_slice,
                total_runs=1,
                output_dir=tmp_path,
                fixtures_dir=tmp_path / "fixtures",
                console_lock=console_lock,
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=1.0,
            )

        # Factory should have been called to create a runner
        assert len(factory.runners_created) >= 1
        # Should produce exactly 1 record
        assert len(records) == 1
        assert records[0].outcome.stop_reason == "goal_achieved"

    @pytest.mark.asyncio
    async def test_worker_factory_create_receives_correct_paths(
        self, simple_scenario: Scenario, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """runner_factory.create() is called with the correct run_dir and fixtures_dir."""
        factory = MockRunnerFactory()
        await factory.start()

        fixtures_dir = tmp_path / "fixtures"
        run_slice = [(simple_scenario, simple_persona, 0)]
        console_lock = asyncio.Lock()

        canned = _make_canned_record(simple_scenario, simple_persona)

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            mock_orch_instance = AsyncMock()
            mock_orch_instance.run = AsyncMock(return_value=canned)
            mock_orch_cls.return_value = mock_orch_instance

            await _worker(
                worker_id=0,
                runner_factory=factory,
                run_slice=run_slice,
                total_runs=1,
                output_dir=tmp_path,
                fixtures_dir=fixtures_dir,
                console_lock=console_lock,
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=1.0,
            )

        # Verify runner was created
        assert len(factory.runners_created) == 1

        # Verify the expected run_dir path was constructed
        expected_folder = run_folder_name(simple_scenario, simple_persona, 0)
        expected_run_dir = tmp_path / "runs" / expected_folder
        assert expected_run_dir.exists()


class TestNoPlaywrightImport:
    def test_experiment_module_has_no_playwright_imports(self) -> None:
        """Verify experiment.py has no playwright imports in its source."""
        import metis.engine.simulation.experiment as mod

        source = inspect.getsource(mod)
        # Should not have 'from playwright' or 'import playwright'
        assert "from playwright" not in source
        assert "import playwright" not in source

    def test_experiment_module_has_no_playwright_runner_import(self) -> None:
        """Verify experiment.py does not import PlaywrightRunner directly."""
        import metis.engine.simulation.experiment as mod

        source = inspect.getsource(mod)
        assert "PlaywrightRunner" not in source
