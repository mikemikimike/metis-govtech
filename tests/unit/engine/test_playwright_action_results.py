"""OrcaPlaywrightRunner satisfies I1: one ActionResult per action (issue #329).

Also covers issue #320: a click or fill the DOM refused used to be logged at
warning level and dropped, so the persona was never told its action failed.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("playwright")

from metis.engine.simulation.gen_1.runners import orca_playwright
from metis.engine.simulation.gen_1.runners.orca_playwright import OrcaPlaywrightRunner
from metis.engine.simulation.gen_1.types import (
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

    def test_delivered_true_is_stated_explicitly_not_left_to_the_default(self) -> None:
        """I5: this runner has no seam that declines a turn before sending it,
        but the value is still written at the call site rather than assumed —
        so a future change to the field's default cannot silently misreport
        this runner as having declined."""
        import inspect

        source = inspect.getsource(orca_playwright._ui_state_to_observation)
        assert "delivered=True" in source


class TestLazySelfHealing:
    """I3 hygiene, relocated from the orchestrator's recover() call (#361)."""

    @pytest.mark.asyncio
    async def test_a_raised_simulation_error_marks_the_page_dirty(
        self, tmp_path, monkeypatch, quiet_page
    ) -> None:
        from metis.engine.simulation.exceptions import TransientDOMError

        async def _boom(_page, _message, _config, timeout_override=None):
            raise TransientDOMError("locator missing")

        monkeypatch.setattr(orca_playwright, "send_message", _boom)
        runner, _ = _make_runner(tmp_path)

        assert runner._page_dirty is False
        with pytest.raises(TransientDOMError):
            await runner.send_turn("hi", [])

        assert runner._page_dirty is True

    @pytest.mark.asyncio
    async def test_a_dirty_page_is_reloaded_before_the_next_turn(
        self, tmp_path, monkeypatch, quiet_page
    ) -> None:
        recover_calls: list[object] = []

        async def _fake_recover_page(page, config):
            recover_calls.append(page)

        monkeypatch.setattr(orca_playwright, "_recover_page", _fake_recover_page)
        runner, _ = _make_runner(tmp_path)
        runner._page_dirty = True

        obs = await runner.send_turn("hi", [])

        assert recover_calls == [runner._page]
        assert runner._page_dirty is False
        assert obs.text == "ok"

    @pytest.mark.asyncio
    async def test_a_clean_page_is_not_reloaded(
        self, tmp_path, monkeypatch, quiet_page
    ) -> None:
        recover_calls: list[object] = []

        async def _fake_recover_page(page, config):
            recover_calls.append(page)

        monkeypatch.setattr(orca_playwright, "_recover_page", _fake_recover_page)
        runner, _ = _make_runner(tmp_path)

        await runner.send_turn("hi", [])

        assert recover_calls == []

    @pytest.mark.asyncio
    async def test_a_failed_reload_keeps_the_page_marked_dirty(
        self, tmp_path, monkeypatch, quiet_page
    ) -> None:
        async def _failing_recover_page(page, config):
            raise RuntimeError("reload timed out")

        monkeypatch.setattr(orca_playwright, "_recover_page", _failing_recover_page)
        runner, _ = _make_runner(tmp_path)
        runner._page_dirty = True

        obs = await runner.send_turn("hi", [])

        assert obs.text == "ok"
        assert runner._page_dirty is True
