"""Old import paths still reach the code that moved into ``simulation.gen_1`` (#475)."""

from __future__ import annotations

import pytest

from metis.engine.simulation import runner as old_runner
from metis.engine.simulation import types as old_types

GEN_1_TYPE_NAMES = [
    "UploadFileAction",
    "ButtonClickAction",
    "FormFillAction",
    "ChosenAction",
    "ActionSlot",
    "UserAgentOutput",
    "FormElement",
    "UIState",
    "ActionResult",
    "Observation",
    "TrialMeta",
    "UserAgentInput",
]


def test_old_runner_path_is_gen_1_runner() -> None:
    from metis.engine.simulation.factory import RunnerFactory
    from metis.engine.simulation.gen_1.runner import Runner

    assert old_runner.Runner is Runner
    assert old_runner.RunnerFactory is RunnerFactory


@pytest.mark.parametrize("name", GEN_1_TYPE_NAMES)
def test_old_types_path_reexports_gen_1_types(name: str) -> None:
    from metis.engine.simulation.gen_1 import types as gen_1_types

    assert getattr(old_types, name) is getattr(gen_1_types, name)


@pytest.mark.parametrize("name", ["Persona", "Scenario", "Specification"])
def test_shared_types_stay_in_shared_module(name: str) -> None:
    assert getattr(old_types, name).__module__ == "metis.engine.simulation.types"
