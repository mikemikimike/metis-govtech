"""Tests for _worker using a mock RunnerFactory."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metis.engine.simulation.exceptions import ConsecutiveFailureEscalation
from metis.engine.simulation.experiment import (
    RunPlanItem,
    _worker,
    run_folder_name,
)
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

        worker_runs = [RunPlanItem(simple_scenario, simple_persona, 1)]
        console_lock = asyncio.Lock()

        canned = _make_canned_record(simple_scenario, simple_persona)

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            mock_orch_instance = AsyncMock()
            mock_orch_instance.run = AsyncMock(return_value=canned)
            mock_orch_cls.return_value = mock_orch_instance

            records = await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=worker_runs,
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
        worker_runs = [RunPlanItem(simple_scenario, simple_persona, 1)]
        console_lock = asyncio.Lock()

        canned = _make_canned_record(simple_scenario, simple_persona)

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            mock_orch_instance = AsyncMock()
            mock_orch_instance.run = AsyncMock(return_value=canned)
            mock_orch_cls.return_value = mock_orch_instance

            await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=worker_runs,
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
        expected_folder = run_folder_name(simple_scenario, simple_persona, 1)
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
        """Verify experiment.py does not import OrcaPlaywrightRunner directly."""
        import metis.engine.simulation.experiment as mod

        source = inspect.getsource(mod)
        assert "OrcaPlaywrightRunner" not in source


def _partial_record(
    scenario: Scenario, persona: Persona, *, turns: int, stop_reason: str
) -> RunRecord:
    """A RunRecord standing in for orchestrator.partial_record() output."""
    return RunRecord(
        config=RunConfig(persona=persona.id, scenario=scenario.id, metric_refs=[]),
        target_session_id="sess-partial",
        outcome=RunOutcome(
            stop_reason=stop_reason,
            total_turns=turns,
            duration_seconds=1.0,
        ),
        conversation=[],
        artifacts_collected=[],
    )


class TestWorkerUnexpectedCrash:
    @pytest.mark.asyncio
    async def test_crash_preserves_partial_turns(
        self, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """On an unexpected crash the recorded turn count comes from the
        orchestrator's partial state, not a zeroed-out record."""
        scenario = Scenario(
            id="test-scenario",
            description="s",
            persona_refs=["tester"],
            num_trials=1,
            max_turns=5,
            max_run_retries=0,  # no retry: isolate preservation
            metric_refs=[],
        )
        factory = MockRunnerFactory()
        await factory.start()

        partial = _partial_record(
            scenario, simple_persona, turns=3, stop_reason="system_error"
        )

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=RuntimeError())  # message-less
            instance.partial_record = MagicMock(return_value=partial)
            mock_orch_cls.return_value = instance

            records = await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=[RunPlanItem(scenario, simple_persona, 1)],
                output_dir=tmp_path,
                fixtures_dir=tmp_path / "fixtures",
                console_lock=asyncio.Lock(),
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=0.0,
            )

        assert len(records) == 1
        assert records[0].outcome.stop_reason == "system_error"
        assert records[0].outcome.total_turns == 3  # preserved, not 0
        assert len(records[0].prior_failures) == 1
        assert records[0].prior_failures[0].turn_reached == 3
        assert records[0].prior_failures[0].failure_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_crash_is_retried_then_succeeds(
        self, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """An unexpected crash on attempt 1 is retried; a successful
        attempt 2 wins, and the crash is recorded in prior_failures."""
        scenario = Scenario(
            id="test-scenario",
            description="s",
            persona_refs=["tester"],
            num_trials=1,
            max_turns=5,
            max_run_retries=1,  # -> max_attempts == 2
            metric_refs=[],
        )
        factory = MockRunnerFactory()
        await factory.start()

        success = _make_canned_record(scenario, simple_persona)
        partial = _partial_record(
            scenario, simple_persona, turns=2, stop_reason="system_error"
        )

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=[RuntimeError(), success])
            instance.partial_record = MagicMock(return_value=partial)
            mock_orch_cls.return_value = instance

            records = await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=[RunPlanItem(scenario, simple_persona, 1)],
                output_dir=tmp_path,
                fixtures_dir=tmp_path / "fixtures",
                console_lock=asyncio.Lock(),
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=0.0,
            )

        assert instance.run.await_count == 2
        assert records[0].outcome.stop_reason == "goal_achieved"
        assert records[0].attempt_number == 2
        assert records[0].total_attempts == 2
        assert len(records[0].prior_failures) == 1
        assert records[0].prior_failures[0].turn_reached == 2

    @pytest.mark.asyncio
    async def test_crash_before_orchestrator_built_falls_back_to_empty(
        self, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """If the crash happens before the Orchestrator is constructed,
        the worker still records a system_error rather than propagating."""
        scenario = Scenario(
            id="test-scenario",
            description="s",
            persona_refs=["tester"],
            num_trials=1,
            max_turns=5,
            max_run_retries=0,
            metric_refs=[],
        )
        factory = MockRunnerFactory()
        await factory.start()

        with patch(
            "metis.engine.simulation.experiment.Orchestrator",
            side_effect=RuntimeError("construction blew up"),
        ):
            records = await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=[RunPlanItem(scenario, simple_persona, 1)],
                output_dir=tmp_path,
                fixtures_dir=tmp_path / "fixtures",
                console_lock=asyncio.Lock(),
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=0.0,
            )

        assert len(records) == 1
        assert records[0].outcome.stop_reason == "system_error"
        assert records[0].outcome.total_turns == 0
        assert records[0].conversation == []

    @pytest.mark.asyncio
    async def test_crash_is_logged_with_traceback(
        self, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """The crash handler uses logger.exception so a traceback is captured."""
        scenario = Scenario(
            id="test-scenario",
            description="s",
            persona_refs=["tester"],
            num_trials=1,
            max_turns=5,
            max_run_retries=0,
            metric_refs=[],
        )
        factory = MockRunnerFactory()
        await factory.start()

        partial = _partial_record(
            scenario, simple_persona, turns=1, stop_reason="system_error"
        )

        with (
            patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls,
            patch("metis.engine.simulation.experiment.logger") as mock_logger,
        ):
            instance = AsyncMock()
            instance.run = AsyncMock(side_effect=RuntimeError())
            instance.partial_record = MagicMock(return_value=partial)
            mock_orch_cls.return_value = instance

            await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=[RunPlanItem(scenario, simple_persona, 1)],
                output_dir=tmp_path,
                fixtures_dir=tmp_path / "fixtures",
                console_lock=asyncio.Lock(),
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=0.0,
            )

        assert mock_logger.exception.called

    @pytest.mark.asyncio
    async def test_recoverable_exhaustion_preserves_partial_turns(
        self, simple_persona: Persona, tmp_path: Path
    ) -> None:
        """When a RunRecoverableError exhausts the retry budget, the recorded
        turn count comes from the orchestrator's partial state, not zero."""
        scenario = Scenario(
            id="test-scenario",
            description="s",
            persona_refs=["tester"],
            num_trials=1,
            max_turns=5,
            max_run_retries=0,  # single attempt — immediately exhausted
            metric_refs=[],
        )
        factory = MockRunnerFactory()
        await factory.start()

        partial = _partial_record(
            scenario, simple_persona, turns=3, stop_reason="system_error"
        )

        with patch("metis.engine.simulation.experiment.Orchestrator") as mock_orch_cls:
            instance = AsyncMock()
            instance.run = AsyncMock(
                side_effect=ConsecutiveFailureEscalation("too many failures")
            )
            instance.partial_record = MagicMock(return_value=partial)
            mock_orch_cls.return_value = instance

            records = await _worker(
                worker_id=0,
                runner_factory=factory,
                worker_runs=[RunPlanItem(scenario, simple_persona, 1)],
                output_dir=tmp_path,
                fixtures_dir=tmp_path / "fixtures",
                console_lock=asyncio.Lock(),
                started_scenarios=set(),
                run_max_retries=2,
                run_retry_delay_seconds=0.0,
            )

        assert len(records) == 1
        assert records[0].outcome.stop_reason == "system_error"
        assert records[0].outcome.total_turns == 3  # preserved, not 0
        assert len(records[0].prior_failures) == 1
        assert records[0].prior_failures[0].turn_reached == 3
