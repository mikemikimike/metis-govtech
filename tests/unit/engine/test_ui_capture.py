"""State-stamping at the two Artifact.model_validate call sites in
_ui_capture.py (#351) — the Playwright runner's own capture/download
behavior is out of scope and untouched."""

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.gen_1.runners.orca_playwright._config import RetryConfig
from metis.engine.simulation.gen_1.runners.orca_playwright._ui_capture import (
    capture_artifacts_panel,
    capture_ui_state,
)


def _make_locator() -> MagicMock:
    """A Playwright ``Locator`` double that matches nothing and is never
    visible, so ``capture_artifacts_panel``'s "More button" / sidebar-trigger
    branches are exercised (count -> 0, is_visible -> False) but never taken,
    letting it fall through to its own ``page.evaluate(...)`` call."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=0)
    locator.nth = MagicMock(return_value=locator)
    locator.first = locator
    locator.is_visible = AsyncMock(return_value=False)
    locator.click = AsyncMock(return_value=None)
    return locator


def _page_returning(value: object) -> MagicMock:
    """A Playwright ``Page`` double whose ``evaluate(...)`` returns ``value``
    (each test below only exercises one of the two capture functions, so a
    single canned return is unambiguous), with the locator/keyboard/timeout
    calls ``capture_artifacts_panel`` makes before reaching its own
    ``page.evaluate(...)`` wired up as no-ops/empty results so that real code
    path actually runs end to end.
    """
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=value)
    page.locator = MagicMock(return_value=_make_locator())
    page.keyboard.press = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock(return_value=None)
    return page


@pytest.mark.asyncio
async def test_capture_ui_state_stamps_unfetched_onto_each_artifact():
    raw = {
        "text": "here are your files",
        "artifacts": [{"name": "a.csv", "path": None}, {"name": "b.csv", "path": None}],
        "target_status_labels": [],
        "errors": [],
        "interactive_elements": [],
        "form_elements": [],
    }
    page = _page_returning(raw)
    state = await capture_ui_state(page, RetryConfig())
    assert [a.state for a in state.artifacts] == ["unfetched", "unfetched"]


@pytest.mark.asyncio
async def test_capture_ui_state_handles_zero_artifacts():
    raw = {
        "text": "no files here",
        "artifacts": [],
        "target_status_labels": [],
        "errors": [],
        "interactive_elements": [],
        "form_elements": [],
    }
    page = _page_returning(raw)
    state = await capture_ui_state(page, RetryConfig())
    assert state.artifacts == []


@pytest.mark.asyncio
async def test_capture_artifacts_panel_stamps_unfetched_onto_each_artifact():
    page = _page_returning([{"name": "c.csv", "path": None}])
    artifacts = await capture_artifacts_panel(page)
    assert [a.state for a in artifacts] == ["unfetched"]


@pytest.mark.asyncio
async def test_capture_artifacts_panel_handles_zero_artifacts():
    page = _page_returning([])
    artifacts = await capture_artifacts_panel(page)
    assert artifacts == []
