"""_download_artifacts must stamp state="received" on a successful download
(#351 follow-up) — before this fix, a downloaded file's `path` was updated
but `state` stayed "unfetched", so every state-gated consumer treated a
genuinely-downloaded artifact as if it never arrived."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("playwright")

from metis.core import Artifact
from metis.engine.simulation.runners.orca_playwright import OrcaPlaywrightRunner
from metis.engine.simulation.runners.orca_playwright._config import (
    AuthConfig,
    OrcaPlaywrightRunnerConfig,
)


class _ExpectDownloadCtx:
    """Doubles Playwright's ``page.expect_download()`` async context manager."""

    def __init__(self, download: MagicMock) -> None:
        self._download = download

    async def __aenter__(self) -> "_ExpectDownloadCtx":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    @property
    def value(self) -> object:
        async def _get() -> MagicMock:
            return self._download

        return _get()


def _make_download(filename: str) -> MagicMock:
    download = MagicMock()
    download.suggested_filename = filename
    download.save_as = AsyncMock(return_value=None)
    return download


def _make_page(*, link_visible: bool, download: MagicMock) -> MagicMock:
    """A Page double where the download-triggering link is visible only
    when `link_visible` is True, driving `_download_artifacts` down either
    its direct-link-click branch or its synthetic-click branch."""
    link = MagicMock()
    link.is_visible = AsyncMock(return_value=link_visible)
    link.click = AsyncMock(return_value=None)
    locator = MagicMock()
    locator.first = link
    page = MagicMock()
    page.locator = MagicMock(return_value=locator)
    page.expect_download = MagicMock(return_value=_ExpectDownloadCtx(download))
    page.evaluate = AsyncMock(return_value=None)
    return page


def _make_runner(page: MagicMock, tmp_path: Path) -> OrcaPlaywrightRunner:
    config = OrcaPlaywrightRunnerConfig(
        url="https://orca.example",
        auth=AuthConfig(username="u", password="p"),
    )
    return OrcaPlaywrightRunner(
        page=page,
        config=config,
        fixtures_dir=tmp_path,
        run_dir=tmp_path,
        experiment_root=tmp_path,
    )


@pytest.mark.asyncio
async def test_download_via_visible_link_stamps_received(tmp_path: Path) -> None:
    download = _make_download("report.csv")
    page = _make_page(link_visible=True, download=download)
    runner = _make_runner(page, tmp_path)
    artifact = Artifact(
        name="report.csv", path="https://orca.example/dl/report.csv", state="unfetched"
    )

    await runner._download_artifacts([artifact])

    assert artifact.state == "received"
    assert artifact.path == "artifacts/report.csv"


@pytest.mark.asyncio
async def test_download_via_synthetic_click_stamps_received(tmp_path: Path) -> None:
    download = _make_download("chart.png")
    page = _make_page(link_visible=False, download=download)
    runner = _make_runner(page, tmp_path)
    artifact = Artifact(
        name="chart.png", path="blob:https://orca.example/abc123", state="unfetched"
    )

    await runner._download_artifacts([artifact])

    assert artifact.state == "received"
    assert artifact.path == "artifacts/chart.png"


@pytest.mark.asyncio
async def test_failed_download_leaves_state_unfetched(tmp_path: Path) -> None:
    download = _make_download("missing.csv")
    download.save_as = AsyncMock(side_effect=RuntimeError("download timed out"))
    page = _make_page(link_visible=True, download=download)
    runner = _make_runner(page, tmp_path)
    artifact = Artifact(
        name="missing.csv",
        path="https://orca.example/dl/missing.csv",
        state="unfetched",
    )

    await runner._download_artifacts([artifact])

    assert artifact.state == "unfetched"
    assert artifact.path is None
