"""Tests for experiment schema contract (runner_factory_ref required)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metis.engine.simulation.types import Specification


def _base_experiment(**overrides: object) -> dict:
    base: dict = {
        "schema_version": 2,
        "id": "test",
        "runner_factory_ref": "tests.unit.engine.test_runner_ref.StubRunnerFactory",
        "personas": [{"id": "p1", "description": "persona", "name": "p1"}],
        "scenarios": [{"id": "s1", "description": "sc", "name": "s1"}],
        "product": {
            "name": "Test product",
            "users": "Test users",
            "description": "Test product",
        },
        "tasks": [
            {
                "id": "TC-001",
                "scenario_ref": "s1",
                "persona_ref": "p1",
                "fixtures": [],
                "num_trials": 1,
                "criterion_refs": ["AC-1-1"],
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
                                "metric_fqn": "metis.library.metrics.TurnBudgetMetric",
                                "metric_args": {},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestSpecificationSchema:
    def test_loads(self) -> None:
        exp = Specification.model_validate(_base_experiment())
        assert exp.schema_version == 2

    def test_wrong_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported schema_version"):
            Specification.model_validate(_base_experiment(schema_version=99))

    def test_runner_factory_ref_required(self) -> None:
        data = _base_experiment()
        del data["runner_factory_ref"]
        with pytest.raises(ValidationError):
            Specification.model_validate(data)

    def test_runner_factory_ref_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Specification.model_validate(_base_experiment(runner_factory_ref=""))

    def test_runner_factory_ref_invalid_fqn_rejected(self) -> None:
        with pytest.raises(ValidationError, match="No module named"):
            Specification.model_validate(
                _base_experiment(runner_factory_ref="nonexistent.Factory")
            )

    def test_runner_factory_ref_valid_fqn_accepted(self) -> None:
        exp = Specification.model_validate(_base_experiment())
        assert (
            exp.runner_factory_ref
            == "tests.unit.engine.test_runner_ref.StubRunnerFactory"
        )
