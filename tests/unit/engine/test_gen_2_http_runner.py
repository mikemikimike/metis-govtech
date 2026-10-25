"""The generic HTTP runner's factory skeleton."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation import trial as seam
from metis.engine.simulation.gen_2 import runner as gen_2_runner
from metis.engine.simulation.gen_2.binding import TargetBindingError
from metis.engine.simulation.gen_2.runners.http import HttpRunnerFactory

if TYPE_CHECKING:
    from pathlib import Path

_BINDING = """\
schema_version: 1
identity: {name: App}
transport: http
spec_url: https://app.example/openapi.json
"""


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    folder = tmp_path / "inputs"
    (folder / "targets").mkdir(parents=True)
    (folder / "targets" / "app.yaml").write_text(_BINDING, encoding="utf-8")
    return folder


def _factory(inputs: Path) -> HttpRunnerFactory:
    specification: Any = SimpleNamespace(target_binding="targets/app.yaml")
    return HttpRunnerFactory.from_specification(specification, inputs)


def test_from_specification_loads_the_binding(inputs: Path) -> None:
    assert _factory(inputs).binding.binding.identity.name == "App"


def test_from_specification_without_a_binding_is_an_error(inputs: Path) -> None:
    specification: Any = SimpleNamespace(target_binding=None)

    with pytest.raises(
        TargetBindingError, match="needs the specification's target_binding"
    ):
        HttpRunnerFactory.from_specification(specification, inputs)


def test_the_factory_runs_on_gen_2(inputs: Path) -> None:
    assert seam.resolve_generation(_factory(inputs)) is seam._GENERATIONS["gen_2"]


def test_retry_defaults_are_the_shared_defaults(inputs: Path) -> None:
    assert _factory(inputs).retry_defaults == (2, 5.0)


@pytest.mark.asyncio
async def test_create_returns_a_gen_2_runner(inputs: Path, tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    factory = HttpRunnerFactory(_factory(inputs).binding, transport=transport)
    await factory.start()

    runner = await factory.create(tmp_path, tmp_path, tmp_path)

    assert isinstance(runner, gen_2_runner.Runner)
    assert runner.session_id is None
    assert await runner.setup(TrialConfig(persona="p", scenario="s")) is None
    assert await runner.teardown() is None
    await factory.close()
