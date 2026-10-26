"""Old import paths still reach the code that moved into ``simulation.gen_1`` (#475)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from metis.engine.simulation import runner as old_runner
from metis.engine.simulation import types as old_types
from metis.engine.simulation.runner_resolver import resolve_runner_factory

SIM = Path(__file__).parents[3] / "packages/engine/src/metis/engine/simulation"
OLD_API = "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
OLD_PW = "metis.engine.simulation.runners.orca_playwright.OrcaPlaywrightRunnerFactory"

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


def test_old_orca_api_ref_resolves_to_gen_1() -> None:
    from metis.engine.simulation.gen_1.runners import orca_api

    assert resolve_runner_factory(OLD_API) is orca_api.OrcaApiRunnerFactory


def test_old_orca_api_path_keeps_its_exports() -> None:
    from metis.engine.simulation.gen_1.runners import orca_api as new
    from metis.engine.simulation.runners import orca_api as old

    assert set(old.__all__) == {
        "FixtureLibrary",
        "FixtureRejected",
        "OrcaApiRunnerConfig",
        "OrcaApiRunner",
        "OrcaApiRunnerFactory",
    }
    for name in old.__all__:
        assert getattr(old, name) is getattr(new, name)


def test_old_orca_playwright_ref_resolves_to_gen_1() -> None:
    pytest.importorskip("playwright")
    from metis.engine.simulation.gen_1.runners import orca_playwright

    assert resolve_runner_factory(OLD_PW) is orca_playwright.OrcaPlaywrightRunnerFactory


def test_orca_playwright_shim_names_gen_1_without_importing_it() -> None:
    # Runs without Playwright: reads the shim's source instead of importing it.
    shim = ast.parse(
        (SIM / "runners/orca_playwright/__init__.py").read_text(encoding="utf-8")
    )
    imports = {
        (n.module, a.name)
        for n in ast.walk(shim)
        if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    target = "metis.engine.simulation.gen_1.runners.orca_playwright"
    assert {
        (target, "OrcaPlaywrightRunner"),
        (target, "OrcaPlaywrightRunnerFactory"),
    } <= imports
    new_src = (SIM / "gen_1/runners/orca_playwright/__init__.py").read_text(
        encoding="utf-8"
    )
    assert "class OrcaPlaywrightRunner(" in new_src
    assert "import OrcaPlaywrightRunnerFactory" in new_src


@pytest.mark.parametrize(
    "old",
    [
        "orchestrator.py",
        "artifact_summarizer.py",
        "_contract.py",
        "user_agent",
        "runners/_http.py",
        "runners/orca_api/_config.py",
        "runners/orca_playwright/_config.py",
    ],
)
def test_moved_module_has_no_old_path(old: str) -> None:
    # Checks files, not imports: importing under the orca_playwright shim needs Playwright.
    assert not (SIM / old).exists()


def test_example_specification_loads() -> None:
    from metis.engine.simulation.types import Specification

    path = SIM.parents[3] / "examples/gen_1-orca_api-1/specification.yaml"
    assert Specification.load_file(path).runner_factory_ref == OLD_API
