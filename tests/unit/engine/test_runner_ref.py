"""Tests for runner_factory_ref field in Specification model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from metis.core.trials import TrialConfig
from metis.engine.simulation.runner import Runner
from metis.engine.simulation.runner_resolver import resolve_runner_factory
from metis.engine.simulation.types import ChosenAction, Observation, Specification


class TestRunnerRefField:
    """Tests for the runner_factory_ref required field on Specification."""

    def _minimal_experiment(self, **overrides) -> dict:
        base = {
            "schema_version": 1,
            "id": "test-exp",
            "runner_factory_ref": "tests.unit.engine.test_runner_ref.StubRunnerFactory",
            "personas": [{"id": "p1", "description": "persona", "name": "p1"}],
            "scenarios": [{"id": "s1", "description": "scenario", "name": "s1"}],
            "target": {
                "name": "Test target",
                "users": "Test users",
                "description": "Test target",
            },
            "tasks": [
                {
                    "id": "TC-001",
                    "scenario_ref": "s1",
                    "persona_ref": "p1",
                    "fixtures": [],
                    "num_trials": 1,
                    "behaviour_refs": ["EB-1"],
                }
            ],
            "features": [
                {
                    "id": "F-1",
                    "name": "Responses",
                    "description": "Responses",
                    "behaviours": [
                        {
                            "id": "EB-1",
                            "name": "Respond",
                            "description": "Respond correctly",
                            "measured": True,
                            "criteria": [
                                {
                                    "id": "AC-1-1",
                                    "name": "Check 1",
                                    "description": {
                                        "given": "a request",
                                        "when": "the agent responds",
                                        "then": "the requirement is met",
                                    },
                                    "grader_fqn": "tests.unit.engine.graders_for_tests.FixedScoreGrader",
                                    "grader_args": {},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        base.update(overrides)
        return base

    def test_runner_factory_ref_required(self) -> None:
        data = self._minimal_experiment()
        del data["runner_factory_ref"]
        with pytest.raises(ValidationError):
            Specification.model_validate(data)

    def test_runner_factory_ref_with_fqn_string(self) -> None:
        # Use the always-importable StubRunnerFactory to test FQN string storage.
        fqn = "tests.unit.engine.test_runner_ref.StubRunnerFactory"
        exp = Specification.model_validate(
            self._minimal_experiment(runner_factory_ref=fqn)
        )
        assert exp.runner_factory_ref == fqn

    def test_runner_factory_ref_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Specification.model_validate(
                self._minimal_experiment(runner_factory_ref="")
            )


class TestResolveRunnerFactory:
    """Tests for dynamic runner factory resolution."""

    def test_resolve_playwright_factory(self) -> None:
        pytest.importorskip("playwright")
        fqn = "metis.engine.simulation.runners.orca_playwright.OrcaPlaywrightRunnerFactory"
        cls = resolve_runner_factory(fqn)
        from metis.engine.simulation.runners.orca_playwright import (
            OrcaPlaywrightRunnerFactory,
        )

        assert cls is OrcaPlaywrightRunnerFactory

    def test_resolve_nonexistent_module_raises_import_error(self) -> None:
        with pytest.raises(ImportError, match="No module named 'nonexistent'"):
            resolve_runner_factory("nonexistent.module.ClassName")

    def test_resolve_nonexistent_class_raises_import_error(self) -> None:
        # Use a module that doesn't need optional deps (runner.py is always importable).
        with pytest.raises(ImportError, match="has no attribute 'NoSuchClass'"):
            resolve_runner_factory("metis.engine.simulation.runner.NoSuchClass")

    def test_resolve_non_factory_raises_type_error(self) -> None:
        with pytest.raises(
            TypeError, match="does not satisfy the RunnerFactory protocol"
        ):
            resolve_runner_factory("builtins.str")

    def test_resolve_fqn_without_dot_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="must be a dotted"):
            resolve_runner_factory("NoDots")


class StubRunner(Runner):
    async def setup(self, config: TrialConfig) -> None:
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

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> Runner:
        return StubRunner()

    async def close(self) -> None:
        StubRunnerFactory.closed = True


class TestRunnerRefCLIIntegration:
    """Verify that runner_factory_ref in specification.yaml selects the correct factory."""

    def test_resolve_from_experiment_uses_custom_factory(self) -> None:
        fqn = "tests.unit.engine.test_runner_ref.StubRunnerFactory"
        from metis.engine.simulation.runner_resolver import resolve_runner_factory

        cls = resolve_runner_factory(fqn)
        assert cls is StubRunnerFactory

    def test_resolve_playwright_factory_from_experiment(self) -> None:
        pytest.importorskip("playwright")
        from metis.engine.simulation.runner_resolver import resolve_runner_factory
        from metis.engine.simulation.runners.orca_playwright import (
            OrcaPlaywrightRunnerFactory,
        )

        fqn = "metis.engine.simulation.runners.orca_playwright.OrcaPlaywrightRunnerFactory"
        cls = resolve_runner_factory(fqn)
        assert cls is OrcaPlaywrightRunnerFactory


class TestRunnerRefValidation:
    """Ensure invalid runner_factory_ref values are caught at Specification parse time."""

    def _minimal_experiment(self, **overrides) -> dict:
        base = {
            "schema_version": 1,
            "id": "test-exp",
            "runner_factory_ref": "tests.unit.engine.test_runner_ref.StubRunnerFactory",
            "personas": [{"id": "p1", "description": "persona", "name": "p1"}],
            "scenarios": [{"id": "s1", "description": "scenario", "name": "s1"}],
            "target": {
                "name": "Test target",
                "users": "Test users",
                "description": "Test target",
            },
            "tasks": [
                {
                    "id": "TC-001",
                    "scenario_ref": "s1",
                    "persona_ref": "p1",
                    "fixtures": [],
                    "num_trials": 1,
                    "behaviour_refs": ["EB-1"],
                }
            ],
            "features": [
                {
                    "id": "F-1",
                    "name": "Responses",
                    "description": "Responses",
                    "behaviours": [
                        {
                            "id": "EB-1",
                            "name": "Respond",
                            "description": "Respond correctly",
                            "measured": True,
                            "criteria": [
                                {
                                    "id": "AC-1-1",
                                    "name": "Check 1",
                                    "description": {
                                        "given": "a request",
                                        "when": "the agent responds",
                                        "then": "the requirement is met",
                                    },
                                    "grader_fqn": "tests.unit.engine.graders_for_tests.FixedScoreGrader",
                                    "grader_args": {},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        base.update(overrides)
        return base

    def test_invalid_module_rejected_at_load(self) -> None:
        with pytest.raises(ValidationError, match="No module named"):
            Specification.model_validate(
                self._minimal_experiment(runner_factory_ref="nonexistent.FakeFactory")
            )

    def test_invalid_class_rejected_at_load(self) -> None:
        # Use an always-importable module so playwright is not required.
        with pytest.raises(ValidationError, match="has no attribute"):
            Specification.model_validate(
                self._minimal_experiment(
                    runner_factory_ref="metis.engine.simulation.runner.NoSuchClass"
                )
            )

    def test_non_factory_rejected_at_load(self) -> None:
        with pytest.raises(ValidationError, match="does not satisfy"):
            Specification.model_validate(
                self._minimal_experiment(runner_factory_ref="builtins.str")
            )

    def test_valid_factory_passes_validation(self) -> None:
        # Use StubRunnerFactory (always importable) to verify that a valid factory passes.
        fqn = "tests.unit.engine.test_runner_ref.StubRunnerFactory"
        exp = Specification.model_validate(
            self._minimal_experiment(runner_factory_ref=fqn)
        )
        assert exp.runner_factory_ref == fqn


class TestExampleExperiment:
    """Verify the shipped example experiment's state after the grader redesign (#428).

    Only AC-EXEC-3 has a grader (the demo TraceBudgetGrader); every other Criterion's
    ``grader_fqn`` is left empty until graders are written for it. The document still parses,
    and the engine refuses to run it, naming exactly those Criteria. When a grader is added
    for a Criterion, this test fails and its expected set shrinks.
    """

    EXAMPLE = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "engine"
        / "example-experiment"
        / "specification.yaml"
    )

    def _document(self) -> dict[str, Any]:
        import yaml

        return yaml.safe_load(self.EXAMPLE.read_text(encoding="utf-8"))

    def test_example_experiment_parses_as_a_document(self) -> None:
        from metis.core.specification import Specification as Document

        document = Document.model_validate(self._document())
        assert document.experiment.id == "orca-eval"
        assert (
            document.experiment.runner_factory_ref
            == "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
        )

    def test_only_the_demo_criterion_has_a_grader(self) -> None:
        from metis.core.specification import Specification as Document

        document = Document.model_validate(self._document())
        graded = {
            c.id: (c.grader_fqn, c.grader_args)
            for b in document.behaviours()
            for c in b.criteria
            if c.grader_fqn
        }
        assert graded == {
            "AC-EXEC-3": ("metis.library.graders.TraceBudgetGrader", {"max_traces": 4})
        }

    def test_the_engine_refuses_it_naming_every_criterion_without_a_grader(
        self,
    ) -> None:
        from metis.core.specification import Specification as Document

        ungraded = {
            c.id
            for b in Document.model_validate(self._document()).behaviours()
            for c in b.criteria
            if not c.grader_fqn
        }
        assert len(ungraded) == 83
        with pytest.raises(ValidationError) as exc_info:
            Specification.load_file(self.EXAMPLE)
        message = str(exc_info.value)
        assert all(f"Criterion {cid} needs a Grader." in message for cid in ungraded)
        assert "AC-EXEC-3 needs a Grader" not in message
