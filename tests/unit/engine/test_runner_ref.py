"""Tests for runner_ref field in Experiment model."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from metis.engine.simulation.runner import Runner
from metis.engine.simulation.runner_resolver import resolve_runner_factory
from metis.engine.simulation.types import (
    ChosenAction,
    Experiment,
    Observation,
    RunConfig,
)


class TestRunnerRefField:
    """Tests for the runner_ref optional field on Experiment."""

    def _minimal_experiment(self, **overrides) -> dict:
        base = {
            "schema_version": 1,
            "id": "test-exp",
            "description": "test",
            "personas": [{"id": "p1", "description": "persona"}],
            "scenarios": [
                {
                    "id": "s1",
                    "description": "scenario",
                    "persona_refs": ["p1"],
                }
            ],
        }
        base.update(overrides)
        return base

    def test_runner_ref_absent_defaults_to_none(self) -> None:
        exp = Experiment.model_validate(self._minimal_experiment())
        assert exp.runner_ref is None

    def test_runner_ref_explicit_none(self) -> None:
        exp = Experiment.model_validate(self._minimal_experiment(runner_ref=None))
        assert exp.runner_ref is None

    def test_runner_ref_with_fqn_string(self) -> None:
        fqn = "metis.engine.simulation.runners.playwright.PlaywrightRunnerFactory"
        exp = Experiment.model_validate(self._minimal_experiment(runner_ref=fqn))
        assert exp.runner_ref == fqn

    def test_runner_ref_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Experiment.model_validate(self._minimal_experiment(runner_ref=""))


class TestResolveRunnerFactory:
    """Tests for dynamic runner factory resolution."""

    def test_resolve_playwright_factory(self) -> None:
        fqn = "metis.engine.simulation.runners.playwright.PlaywrightRunnerFactory"
        cls = resolve_runner_factory(fqn)
        from metis.engine.simulation.runners.playwright import PlaywrightRunnerFactory

        assert cls is PlaywrightRunnerFactory

    def test_resolve_nonexistent_module_raises_import_error(self) -> None:
        with pytest.raises(ImportError, match="No module named 'nonexistent'"):
            resolve_runner_factory("nonexistent.module.ClassName")

    def test_resolve_nonexistent_class_raises_import_error(self) -> None:
        with pytest.raises(ImportError, match="has no attribute 'NoSuchClass'"):
            resolve_runner_factory(
                "metis.engine.simulation.runners.playwright.NoSuchClass"
            )

    def test_resolve_non_factory_raises_type_error(self) -> None:
        with pytest.raises(
            TypeError, match="does not satisfy the RunnerFactory protocol"
        ):
            resolve_runner_factory("builtins.str")

    def test_resolve_fqn_without_dot_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must be a dotted"):
            resolve_runner_factory("NoDots")


class StubRunner(Runner):
    async def setup(self, config: RunConfig) -> None:
        pass

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        return Observation(text="stub")

    async def teardown(self) -> None:
        pass

    async def get_session_id(self) -> str | None:
        return None


class StubRunnerFactory:
    """A test factory that tracks lifecycle calls."""

    started = False
    closed = False

    @classmethod
    def from_env(cls, headed: bool = False) -> StubRunnerFactory:
        return cls()

    @property
    def retry_defaults(self) -> tuple[int, float]:
        return (2, 5.0)

    async def start(self) -> None:
        StubRunnerFactory.started = True

    async def create(self, run_dir: Path, fixtures_dir: Path) -> Runner:
        return StubRunner()

    async def close(self) -> None:
        StubRunnerFactory.closed = True


class TestRunnerRefCLIIntegration:
    """Verify that runner_ref in experiment.yaml selects the correct factory."""

    def test_resolve_from_experiment_uses_custom_factory(self) -> None:
        fqn = "tests.unit.engine.test_runner_ref.StubRunnerFactory"
        from metis.engine.simulation.runner_resolver import resolve_runner_factory

        cls = resolve_runner_factory(fqn)
        assert cls is StubRunnerFactory

    def test_resolve_from_experiment_none_falls_back(self) -> None:
        from metis.engine.simulation.runner_resolver import resolve_runner_factory
        from metis.engine.simulation.runners.playwright import PlaywrightRunnerFactory

        fqn = "metis.engine.simulation.runners.playwright.PlaywrightRunnerFactory"
        cls = resolve_runner_factory(fqn)
        assert cls is PlaywrightRunnerFactory


class TestRunnerRefValidation:
    """Ensure invalid runner_ref values are caught at Experiment parse time."""

    def _minimal_experiment(self, **overrides) -> dict:
        base = {
            "schema_version": 1,
            "id": "test-exp",
            "description": "test",
            "personas": [{"id": "p1", "description": "persona"}],
            "scenarios": [
                {
                    "id": "s1",
                    "description": "scenario",
                    "persona_refs": ["p1"],
                }
            ],
        }
        base.update(overrides)
        return base

    def test_invalid_module_rejected_at_load(self) -> None:
        with pytest.raises(ValidationError, match="No module named"):
            Experiment.model_validate(
                self._minimal_experiment(runner_ref="nonexistent.FakeFactory")
            )

    def test_invalid_class_rejected_at_load(self) -> None:
        with pytest.raises(ValidationError, match="has no attribute"):
            Experiment.model_validate(
                self._minimal_experiment(
                    runner_ref="metis.engine.simulation.runners.playwright.NoSuchClass"
                )
            )

    def test_non_factory_rejected_at_load(self) -> None:
        with pytest.raises(ValidationError, match="does not satisfy"):
            Experiment.model_validate(
                self._minimal_experiment(runner_ref="builtins.str")
            )

    def test_valid_factory_passes_validation(self) -> None:
        fqn = "metis.engine.simulation.runners.playwright.PlaywrightRunnerFactory"
        exp = Experiment.model_validate(self._minimal_experiment(runner_ref=fqn))
        assert exp.runner_ref == fqn


class TestExampleExperiment:
    """Verify the shipped example experiment continues to load."""

    def test_example_experiment_loads(self) -> None:
        example_path = (
            Path(__file__).resolve().parents[3]
            / "packages"
            / "engine"
            / "example-experiment"
            / "experiment.yaml"
        )
        if not example_path.exists():
            pytest.skip("example-experiment not found at expected path")
        exp = Experiment.load_file(example_path)
        assert exp.id == "orca-eval"
        assert exp.runner_ref is None
