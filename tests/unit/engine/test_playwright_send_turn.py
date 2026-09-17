"""Upload-validation tests for the Orca Playwright runner (issue #311)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.runners.orca_playwright import OrcaPlaywrightRunner
from metis.engine.simulation.types import Observation, UploadFileAction


def _make_runner(tmp_path, fixtures=()):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    runner = OrcaPlaywrightRunner(Mock(), Mock(), fixtures_dir, run_dir, tmp_path)
    runner._fixtures = list(fixtures)
    return runner, fixtures_dir


@pytest.mark.asyncio
async def test_send_turn_rejects_non_fixture_upload(tmp_path) -> None:
    runner, _ = _make_runner(tmp_path, fixtures=["sales.csv"])
    obs = await runner.send_turn(
        "hi", [UploadFileAction(slot_id="ghost.csv", filename="ghost.csv")]
    )
    assert isinstance(obs, Observation)
    assert obs.errors and "ghost.csv" in obs.errors[0]


@pytest.mark.asyncio
async def test_send_turn_rejects_missing_file_upload(tmp_path) -> None:
    runner, _ = _make_runner(tmp_path, fixtures=["sales.csv"])
    # scenario fixture, but no file on disk
    obs = await runner.send_turn(
        "hi", [UploadFileAction(slot_id="sales.csv", filename="sales.csv")]
    )
    assert isinstance(obs, Observation)
    assert obs.errors and "sales.csv" in obs.errors[0]


@pytest.mark.asyncio
async def test_send_turn_rejects_directory_named_like_fixture(tmp_path) -> None:
    # A directory sharing a fixture's name must not pass as an uploadable file
    # (matches OrcaApiRunner._fixture_path, which requires is_file()).
    runner, fixtures_dir = _make_runner(tmp_path, fixtures=["report"])
    (fixtures_dir / "report").mkdir()
    obs = await runner.send_turn(
        "hi", [UploadFileAction(slot_id="report", filename="report")]
    )
    assert isinstance(obs, Observation)
    assert obs.errors and "report" in obs.errors[0]
