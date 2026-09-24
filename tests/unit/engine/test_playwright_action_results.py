"""OrcaPlaywrightRunner satisfies I1: one ActionResult per action (issue #329).

Also covers issue #320: a click or fill the DOM refused used to be logged at
warning level and dropped, so the persona was never told its action failed.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.runners import orca_playwright
from metis.engine.simulation.runners.orca_playwright import OrcaPlaywrightRunner
from metis.engine.simulation.types import (
    ButtonClickAction,
    FormFillAction,
    UIState,
    UploadFileAction,
)


def _make_runner(tmp_path, page=None):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    runner = OrcaPlaywrightRunner(
        page or Mock(), Mock(), fixtures_dir, run_dir, tmp_path
    )
    return runner, fixtures_dir


@pytest.fixture
def quiet_page(monkeypatch):
    """Stub the post-loop DOM work so a test can stop at the action loop.

    ``auto_fill_and_submit`` returning False keeps ``has_form_submit`` false,
    and a reply of "ok" matches none of the artifact-hint keywords, so the
    artifacts panel is never consulted either.
    """

    async def _no_auto_fill(_page):
        return False

    async def _reply(_page, _message, _config, timeout_override=None):
        return UIState(text="ok")

    async def _no_charts(_page, _dir):
        return None

    monkeypatch.setattr(orca_playwright, "auto_fill_and_submit", _no_auto_fill)
    monkeypatch.setattr(orca_playwright, "send_message", _reply)
    monkeypatch.setattr(orca_playwright, "capture_inline_charts", _no_charts)


# An upload naming a fixture this scenario never staged no longer reaches this
# runner at all: the orchestrator withholds it before send_turn (see
# withhold_unstaged_uploads and its tests in test_runner_contract.py). The
# up-front rejection this file used to cover is gone with it.


class TestTheActionLoopReportsWhatItDropped:
    @pytest.mark.asyncio
    async def test_a_duplicate_upload_is_reported_not_silently_skipped(
        self, tmp_path, quiet_page
    ) -> None:
        runner, fixtures_dir = _make_runner(tmp_path)
        (fixtures_dir / "sales.csv").write_text("a,b\n1,2\n")
        runner._uploaded_files.add("sales.csv")
        obs = await runner.send_turn(
            "hi", [UploadFileAction(slot_id="sales.csv", filename="sales.csv")]
        )
        assert len(obs.action_results) == 1
        assert not obs.action_results[0].succeeded
        assert "already" in obs.action_results[0].detail
        assert obs.action_results[0].retryable is False

    @pytest.mark.asyncio
    async def test_a_click_the_dom_refused_is_reported(
        self, tmp_path, quiet_page
    ) -> None:
        page = Mock()
        page.locator.side_effect = RuntimeError("element not found")
        page.get_by_text.side_effect = RuntimeError("element not found")
        runner, _ = _make_runner(tmp_path, page=page)
        # A label that does not look like a submit, so the turn does not enter
        # the processing wait — this test is about the refused click, not timing.
        obs = await runner.send_turn("hi", [ButtonClickAction(slot_id="Show details")])
        assert not obs.action_results[0].succeeded
        assert obs.action_results[0].detail
        assert obs.action_results[0].retryable is True

    @pytest.mark.asyncio
    async def test_a_fill_the_dom_refused_is_reported(
        self, tmp_path, quiet_page
    ) -> None:
        page = Mock()
        page.locator.side_effect = RuntimeError("element not found")
        runner, _ = _make_runner(tmp_path, page=page)
        obs = await runner.send_turn("hi", [FormFillAction(slot_id="#qty", value="12")])
        assert not obs.action_results[0].succeeded
        assert obs.action_results[0].retryable is True

    @pytest.mark.asyncio
    async def test_no_actions_means_no_rows_and_an_observed_action_list(
        self, tmp_path, quiet_page
    ) -> None:
        runner, _ = _make_runner(tmp_path)
        obs = await runner.send_turn("hi", [])
        assert obs.action_results == []
        # The reply was captured, so [] here means "looked, found none".
        assert obs.available_actions == []


class TestScrapedErrorTextIsATurnNotice:
    def test_ui_state_errors_become_response_notices(self) -> None:
        ui_state = UIState(text="hi", errors=["Something went wrong"])
        obs = orca_playwright._ui_state_to_observation(ui_state, [])
        assert obs.response_notices == ["Something went wrong"]
