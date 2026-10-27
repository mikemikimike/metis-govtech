"""gen_2 plugged into the seam: registration, the trial it builds, and fixture facts (#480)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation import trial as seam
from metis.engine.simulation.artifacts import file_facts
from metis.engine.simulation.gen_2.orchestrator import Orchestrator
from metis.engine.simulation.gen_2.trial import (
    build_trial,
    resolve_fixture_descriptions,
)
from metis.engine.simulation.llm_calls import LLMCallLog
from metis.engine.simulation.types import Persona, Scenario

if TYPE_CHECKING:
    from pathlib import Path


class _Gen2Factory:
    generation = "gen_2"

    async def start(self) -> None:
        pass

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> Any:
        return MagicMock()

    async def close(self) -> None:
        pass


def _kwargs(tmp_path: Path) -> dict[str, Any]:
    return {
        "runner": MagicMock(),
        "persona": Persona(id="p1", name="p1", description="d"),
        "scenario": Scenario(id="s1", description="g", persona_refs=["p1"]),
        "trial_config": TrialConfig(persona="p1", scenario="s1"),
        "run_dir": tmp_path / "t1",
        "fixtures_dir": tmp_path,
        "experiment_root": tmp_path,
        "fixture_artifacts": [],
        "trial_index": 1,
        "state": None,
        "tui_ctx": None,
        "shutdown_event": None,
    }


def test_gen_2_is_registered_beside_gen_1() -> None:
    assert sorted(seam._GENERATIONS) == ["gen_1", "gen_2"]
    assert seam._GENERATIONS["gen_2"].build_trial is build_trial
    assert (
        seam._GENERATIONS["gen_2"].resolve_fixture_descriptions
        is resolve_fixture_descriptions
    )


def test_a_gen_2_factory_gets_a_gen_2_trial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    trial = seam.create_trial(_Gen2Factory(), **_kwargs(tmp_path))

    assert isinstance(trial, Orchestrator)


@pytest.mark.asyncio
async def test_fixture_descriptions_are_file_facts_with_no_llm_call(
    tmp_path: Path,
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "q3.csv").write_text("a,b\n1,2\n3,4\n")
    (fixtures / "notes.md").write_text("hello")

    described = await resolve_fixture_descriptions(
        ["q3.csv", "notes.md", "q3.csv", "missing.txt"], fixtures, tmp_path, {}
    )

    assert described == {
        "q3.csv": file_facts(fixtures / "q3.csv", "q3.csv"),
        "notes.md": file_facts(fixtures / "notes.md", "notes.md"),
    }
    assert "2 data rows, 2 columns; header: a,b" in described["q3.csv"]
    assert not LLMCallLog.for_experiment(tmp_path).path.exists()


@pytest.mark.asyncio
async def test_an_author_description_wins_over_facts(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "q3.csv").write_text("a\n1\n")

    described = await resolve_fixture_descriptions(
        ["q3.csv"], fixtures, tmp_path, {"q3.csv": "Quarterly sales, written by hand"}
    )

    assert described == {"q3.csv": "Quarterly sales, written by hand"}
