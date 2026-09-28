"""OrcaApiRunner satisfies I1: one ActionResult per received action (issue #329)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from metis.engine.simulation.runners.orca_api import (
    OrcaApiRunner,
    OrcaApiRunnerConfig,
)
from metis.engine.simulation.types import (
    ButtonClickAction,
    FormFillAction,
    Observation,
    UploadFileAction,
)


async def _no_sleep(_seconds: float) -> None:
    return None


def _make_runner(
    tmp_path: Path,
    handler: Any = None,
    *,
    fixtures: list[str] | None = None,
) -> OrcaApiRunner:
    """A runner whose transport is ``handler`` and whose scenario stages ``fixtures``."""
    config = OrcaApiRunnerConfig(
        base_url="https://orca.example.com",
        api_key="test-key",
        poll_interval_ms=1,
    )
    client = httpx.AsyncClient(
        base_url="https://orca.example.com/api/v1/",
        transport=httpx.MockTransport(handler) if handler else None,
    )
    for directory in ("fixtures", "run"):
        (tmp_path / directory).mkdir(exist_ok=True)
    runner = OrcaApiRunner(
        client,
        config,
        fixtures_dir=tmp_path / "fixtures",
        run_dir=tmp_path / "run",
        experiment_root=tmp_path,
        sleep=_no_sleep,
    )
    runner._fixtures = list(fixtures or [])
    return runner


def _indices(observation: Observation) -> list[int]:
    return [row.action_index for row in observation.action_results]


class TestCompleteness:
    """I1 — one row per received action, ascending, index equal to position."""

    @pytest.mark.asyncio
    async def test_a_rejected_upload_still_accounts_for_every_action(
        self, tmp_path: Path
    ) -> None:
        """I5: a resolved attachment costs nothing when a sibling fails to
        resolve — the message is still sent, and the failed row carries why."""
        runner = _make_runner(tmp_path, fixtures=["sales.csv"])
        actions = [
            ButtonClickAction(slot_id="send"),
            UploadFileAction(slot_id="ghost.csv", filename="ghost.csv"),
        ]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("hi", actions)
        assert isinstance(body, dict)
        assert body["message"] == "hi"
        assert "files" not in body  # nothing resolved to attach
        assert _indices_of(runner) == [0, 1]
        assert not runner._action_results[0].succeeded  # invented button
        assert not runner._action_results[1].succeeded  # ghost.csv never existed
        assert "ghost.csv" in runner._action_results[1].detail

    @pytest.mark.asyncio
    async def test_a_failed_attachment_does_not_cost_a_later_one_in_the_same_batch(
        self, tmp_path: Path
    ) -> None:
        """I5: the batch's one failure must not swallow a sibling that
        resolved fine — checked with the failure listed first, to rule out
        an ordering bug in how ``file_ids`` gets built."""
        runner = _make_runner(tmp_path, fixtures=["ghost.csv", "sales.csv"])
        (tmp_path / "fixtures" / "sales.csv").write_text("region,total\nnorth,10\n")
        runner._fixture_library._entries["sales.csv"] = "file-123"
        actions = [
            UploadFileAction(slot_id="ghost.csv", filename="ghost.csv"),
            UploadFileAction(slot_id="sales.csv", filename="sales.csv"),
        ]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("please compare these", actions)
        assert isinstance(body, dict)
        assert body["message"] == "please compare these"
        assert body["files"] == ["file-123"]
        assert not runner._action_results[0].succeeded
        assert "ghost.csv" in runner._action_results[0].detail
        assert runner._action_results[1].succeeded

    @pytest.mark.asyncio
    async def test_a_button_click_is_reported_not_merely_logged(
        self, tmp_path: Path
    ) -> None:
        """This runner offers no buttons, so a button the persona invents must
        come back as a failure rather than a warning nobody downstream sees.
        This is issue #320's shape in the API runner."""
        runner = _make_runner(tmp_path)
        runner._plan_actions([ButtonClickAction(slot_id="go")])
        body = await runner._build_submit_body("hi", [ButtonClickAction(slot_id="go")])
        # The turn is still submitted — the message is valid on its own.
        assert isinstance(body, dict)
        assert _indices_of(runner) == [0]
        assert not runner._action_results[0].succeeded
        assert runner._action_results[0].detail

    @pytest.mark.asyncio
    async def test_an_invented_button_does_not_cost_a_resolved_upload(
        self, tmp_path: Path
    ) -> None:
        """The abandon guard belongs to the attachments, not to the whole turn.

        A turn that loses an attachment is not the turn the persona composed, so
        it is abandoned. An invented button contributes nothing to the body, so
        the message is still exactly what the persona wrote and must be sent —
        the same rule the test above states for a turn with no upload in it.
        Seeding the fixture cache resolves the upload without HTTP, keeping this
        test on the guard rather than on upload mechanics.
        """
        runner = _make_runner(tmp_path, fixtures=["sales.csv"])
        (tmp_path / "fixtures" / "sales.csv").write_text("region,total\nnorth,10\n")
        runner._fixture_library._entries["sales.csv"] = "file-123"
        actions = [
            ButtonClickAction(slot_id="go"),
            UploadFileAction(slot_id="sales.csv", filename="sales.csv"),
        ]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("please chart this", actions)
        assert isinstance(body, dict)
        assert body["files"] == ["file-123"]
        assert not runner._action_results[0].succeeded  # the button never existed
        assert runner._action_results[1].succeeded  # the upload resolved


def _indices_of(runner: OrcaApiRunner) -> list[int]:
    return [row.action_index for row in runner._action_results]


class TestFormProblemAttribution:
    @pytest.mark.asyncio
    async def test_a_mistyped_number_is_blamed_on_the_answering_action(
        self, tmp_path: Path
    ) -> None:
        """I5: the bad answer costs its own row; the message is still sent."""
        runner = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [{"id": "qty", "type": "number", "label": "How many?"}],
        }
        actions = [FormFillAction(slot_id="qty", value="lots")]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("prose", actions)
        assert isinstance(body, dict)
        assert body["message"] == "prose"
        assert "formAnswers" not in body
        assert not runner._action_results[0].succeeded
        assert "expects a number" in runner._action_results[0].detail
        # The row carries it; the turn-level channel does not repeat it.
        assert not any("expects a number" in n for n in runner._pre_submit_notices)

    @pytest.mark.asyncio
    async def test_a_valid_sibling_answer_is_also_failed_when_the_batch_is_discarded(
        self, tmp_path: Path
    ) -> None:
        """I2: ``form_answers`` is cleared for the whole batch, so a valid
        sibling never reaches Orca either — it must not stay succeeded=True
        just because ``_attribute_form_problems`` had nothing to blame it
        for."""
        runner = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [
                {"id": "qty", "type": "number", "label": "How many?"},
                {"id": "why", "type": "text", "label": "Why?"},
            ],
        }
        actions = [
            FormFillAction(slot_id="qty", value="lots"),
            FormFillAction(slot_id="why", value="because"),
        ]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("prose", actions)
        assert isinstance(body, dict)
        assert "formAnswers" not in body
        assert not runner._action_results[0].succeeded
        assert "expects a number" in runner._action_results[0].detail
        assert not runner._action_results[1].succeeded
        assert "sibling" in runner._action_results[1].detail

    @pytest.mark.asyncio
    async def test_an_unanswered_required_field_is_a_notice_not_a_row(
        self, tmp_path: Path
    ) -> None:
        """No action answered it, so no row can own it without inventing one.

        I5: a required field left unanswered no longer costs the turn — the
        message is still sent, and the notice surfaces once the turn settles.
        """
        runner = _make_runner(
            tmp_path,
            lambda request: (
                httpx.Response(200, json={"turnId": "t1", "sessionId": "s1"})
                if request.method == "POST"
                else httpx.Response(200, json={"status": "completed", "output": "ok"})
            ),
        )
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [
                {"id": "qty", "type": "number", "label": "How many?"},
                {"id": "why", "type": "text", "label": "Why?", "required": True},
            ],
        }
        actions = [FormFillAction(slot_id="qty", value="lots")]
        observation = await runner.send_turn("prose", actions)
        assert any("required field 'why'" in n for n in observation.response_notices)
        assert observation.delivered is True

    @pytest.mark.asyncio
    async def test_an_unanswered_required_field_is_a_notice_even_with_an_empty_message(
        self, tmp_path: Path
    ) -> None:
        """The empty-message early return must not swallow a pre-submit notice.

        Nothing is left to send this turn (I5: delivered=False), but the
        problem that made the form answer unusable must still surface.
        """
        runner = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [
                {"id": "qty", "type": "number", "label": "How many?"},
                {"id": "why", "type": "text", "label": "Why?", "required": True},
            ],
        }
        actions = [FormFillAction(slot_id="qty", value="lots")]
        runner._plan_actions(actions)
        result = await runner._build_submit_body("   ", actions)
        assert isinstance(result, Observation)
        assert result.delivered is False
        assert any("required field 'why'" in n for n in result.response_notices)
        assert any("empty" in n for n in result.response_notices)


class TestStatusIsNotAnActionFailure:
    @pytest.mark.asyncio
    async def test_a_guardrail_block_leaves_delivered_actions_succeeded(
        self, tmp_path: Path
    ) -> None:
        """P2: the actions were delivered. The target's refusal is content."""
        runner = _make_runner(tmp_path)
        runner._plan_actions([ButtonClickAction(slot_id="x")])
        observation = await runner._build_observation(
            {"status": "failed", "error": "Blocked by a content guardrail"}
        )
        assert observation.action_results[0].succeeded
        assert any("guardrail" in n for n in observation.response_notices)

    @pytest.mark.asyncio
    async def test_a_cancelled_turn_is_a_notice_too(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        observation = await runner._build_observation(
            {"status": "cancelled", "output": "half an ans"}
        )
        assert observation.text == ""
        assert any("cancelled" in n for n in observation.response_notices)


class TestTurnLevelProblemsWithNoActions:
    @pytest.mark.asyncio
    async def test_an_empty_message_with_no_actions_is_a_notice(
        self, tmp_path: Path
    ) -> None:
        """Reachable with zero actions, so there is no row to carry it."""
        runner = _make_runner(tmp_path)
        runner._plan_actions([])
        result = await runner._build_submit_body("   ", [])
        assert isinstance(result, Observation)
        assert result.action_results == []
        assert any("empty" in n for n in result.response_notices)
        assert result.available_actions is not None
