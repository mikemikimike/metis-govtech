"""Tests for experiment schema contract (runner_factory_ref required)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metis.engine.simulation.types import Experiment


def _base_experiment(**overrides: object) -> dict:
    base: dict = {
        "schema_version": 1,
        "id": "test",
        "description": "test",
        "runner_factory_ref": "tests.unit.engine.test_runner_ref.StubRunnerFactory",
        "personas": [{"id": "p1", "description": "persona"}],
        "scenarios": [{"id": "s1", "description": "sc", "persona_refs": ["p1"]}],
    }
    base.update(overrides)
    return base


class TestExperimentSchema:
    def test_loads(self) -> None:
        exp = Experiment.model_validate(_base_experiment())
        assert exp.schema_version == 1

    def test_wrong_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported schema_version"):
            Experiment.model_validate(_base_experiment(schema_version=99))

    def test_runner_factory_ref_required(self) -> None:
        data = _base_experiment()
        del data["runner_factory_ref"]
        with pytest.raises(ValidationError):
            Experiment.model_validate(data)

    def test_runner_factory_ref_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Experiment.model_validate(_base_experiment(runner_factory_ref=""))

    def test_runner_factory_ref_invalid_fqn_rejected(self) -> None:
        with pytest.raises(ValidationError, match="No module named"):
            Experiment.model_validate(
                _base_experiment(runner_factory_ref="nonexistent.Factory")
            )

    def test_runner_factory_ref_valid_fqn_accepted(self) -> None:
        exp = Experiment.model_validate(_base_experiment())
        assert (
            exp.runner_factory_ref
            == "tests.unit.engine.test_runner_ref.StubRunnerFactory"
        )
