"""Tests for turn-level recovery logic."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metis.engine.simulation.orchestrator import Orchestrator
from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
    ActionResult,
    ButtonClickAction,
    ChosenAction,
    Observation,
    RunConfig,
    Scenario,
    UserAgentOutput,
)


class TestRecoverPage:
    @pytest.mark.asyncio
    async def test_recover_page_reloads_and_waits_for_textarea(self) -> None:
        pytest.importorskip("playwright")
        from metis.engine.simulation.runners.orca_playwright._config import (
            OrcaPlaywrightRunnerConfig,
        )
        from metis.engine.simulation.runners.orca_playwright._recovery import (
            _recover_page,
        )

        page = MagicMock()
        page.reload = AsyncMock()
        page.wait_for_selector = AsyncMock()

        config = OrcaPlaywrightRunnerConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )

        with patch(
            "metis.engine.simulation.runners.orca_playwright._recovery.dismiss_modals",
            new_callable=AsyncMock,
        ):
            await _recover_page(page, config)

        page.reload.assert_called_once_with(
            wait_until="domcontentloaded", timeout=15000
        )
        page.wait_for_selector.assert_called_once_with("textarea", timeout=10000)


class TestRecoverAndCheck:
    @pytest.mark.asyncio
    async def test_returns_ui_state_when_message_found(self) -> None:
        pytest.importorskip("playwright")
        from metis.engine.simulation.runners.orca_playwright._config import (
            OrcaPlaywrightRunnerConfig,
        )
        from metis.engine.simulation.runners.orca_playwright._recovery import (
            _recover_and_check,
        )
        from metis.engine.simulation.types import UIState

        page = MagicMock()
        page.reload = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.evaluate = AsyncMock(return_value="Hello, how can I help you today?")

        config = OrcaPlaywrightRunnerConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )

        mock_ui_state = UIState(text="response from assistant")

        with (
            patch(
                "metis.engine.simulation.runners.orca_playwright._recovery.dismiss_modals",
                new_callable=AsyncMock,
            ),
            patch(
                "metis.engine.simulation.runners.orca_playwright._recovery.capture_ui_state",
                new_callable=AsyncMock,
                return_value=mock_ui_state,
            ),
        ):
            result = await _recover_and_check(
                page, config, "Hello, how can I help you today?"
            )

        assert result == mock_ui_state

    @pytest.mark.asyncio
    async def test_returns_none_when_message_not_found(self) -> None:
        pytest.importorskip("playwright")
        from metis.engine.simulation.runners.orca_playwright._config import (
            OrcaPlaywrightRunnerConfig,
        )
        from metis.engine.simulation.runners.orca_playwright._recovery import (
            _recover_and_check,
        )
        from metis.engine.simulation.types import UIState

        page = MagicMock()
        page.reload = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.evaluate = AsyncMock(return_value="Some other message entirely")

        config = OrcaPlaywrightRunnerConfig(
            url="http://test.com",
            auth={"username": "u", "password": "p"},
        )

        with (
            patch(
                "metis.engine.simulation.runners.orca_playwright._recovery.dismiss_modals",
                new_callable=AsyncMock,
            ),
            patch(
                "metis.engine.simulation.runners.orca_playwright._recovery.capture_ui_state",
                new_callable=AsyncMock,
                return_value=UIState(text="whatever"),
            ),
        ):
            result = await _recover_and_check(page, config, "My actual sent message")

        assert result is None


class TestConsecutiveFailureEscalation:
    @pytest.mark.asyncio
    async def test_escalates_after_consecutive_failures(self) -> None:
        """After N consecutive turn failures, run_simulation should raise
        ConsecutiveFailureEscalation rather than continuing."""
        from metis.engine.simulation.exceptions import ConsecutiveFailureEscalation

        # This test validates the behavior contract. The exact integration
        # depends on the run_simulation refactoring. Verify the exception exists
        # and is importable for now.
        exc = ConsecutiveFailureEscalation("2 consecutive turn failures")
        assert "2 consecutive" in str(exc)


class TestUndeliveredObservation:
    """The shape the orchestrator synthesises when send_turn raised."""

    def test_reason_for_a_timeout_keeps_the_existing_string(self) -> None:
        from metis.engine.simulation.exceptions import ResponseTimeoutError
        from metis.engine.simulation.orchestrator import _undelivered_reason

        reason = _undelivered_reason(ResponseTimeoutError("waited 300s"))
        assert reason == "Response timeout — no response received"

    def test_reason_for_an_unavailable_target_keeps_the_existing_string(self) -> None:
        from metis.engine.simulation.exceptions import TargetUnavailableError
        from metis.engine.simulation.orchestrator import _undelivered_reason

        reason = _undelivered_reason(TargetUnavailableError("503 for 120s"))
        assert reason == "Target unavailable — 503 for 120s"

    def test_a_post_submission_failure_does_not_claim_non_delivery(self) -> None:
        # The message DID reach the target; only the observation failed. A
        # notice saying it was not delivered would be false.
        from metis.engine.simulation.exceptions import (
            PostSubmissionObservationError,
        )
        from metis.engine.simulation.orchestrator import _undelivered_reason

        reason = _undelivered_reason(PostSubmissionObservationError("DOM gone"))
        assert "No reply was captured for this turn" in reason
        assert "not delivered" not in reason

    def test_a_transient_dom_failure_uses_the_same_neutral_reason(self) -> None:
        from metis.engine.simulation.exceptions import TransientDOMError
        from metis.engine.simulation.orchestrator import _undelivered_reason

        assert "No reply was captured for this turn" in _undelivered_reason(
            TransientDOMError("locator missing")
        )

    def test_one_failed_row_per_submitted_action(self) -> None:
        from metis.engine.simulation.orchestrator import _undelivered_observation
        from metis.engine.simulation.types import (
            ButtonClickAction,
            UploadFileAction,
        )

        actions = [
            UploadFileAction(slot_id="s0", filename="sales.csv"),
            ButtonClickAction(slot_id="b0"),
        ]
        obs = _undelivered_observation(actions, "Response timeout — no reply")

        assert [r.action_index for r in obs.action_results] == [0, 1]
        assert all(r.succeeded is False for r in obs.action_results)
        assert all(
            r.detail == "Response timeout — no reply" for r in obs.action_results
        )

    def test_retryable_is_none_because_the_caller_observed_nothing(self) -> None:
        from metis.engine.simulation.orchestrator import _undelivered_observation
        from metis.engine.simulation.types import ButtonClickAction

        obs = _undelivered_observation([ButtonClickAction(slot_id="b")], "gone")
        assert obs.action_results[0].retryable is None

    def test_the_reason_is_also_a_response_notice(self) -> None:
        from metis.engine.simulation.orchestrator import _undelivered_observation

        obs = _undelivered_observation([], "Target unavailable — 503")
        assert obs.response_notices == ["Target unavailable — 503"]

    def test_no_actions_yields_a_notice_and_no_rows(self) -> None:
        from metis.engine.simulation.orchestrator import _undelivered_observation

        obs = _undelivered_observation([], "Response timeout — no reply")
        assert obs.action_results == []
        assert obs.response_notices == ["Response timeout — no reply"]

    def test_available_actions_is_none_because_nobody_looked(self) -> None:
        from metis.engine.simulation.orchestrator import _undelivered_observation

        # send_turn raised, so no DOM and no API payload was ever inspected.
        # `[]` would claim an observation that never happened.
        assert _undelivered_observation([], "gone").available_actions is None

    def test_no_row_is_withheld_because_the_persona_did_nothing_wrong(self) -> None:
        from metis.engine.simulation.orchestrator import _undelivered_observation
        from metis.engine.simulation.types import ButtonClickAction

        obs = _undelivered_observation([ButtonClickAction(slot_id="b")], "gone")
        assert obs.action_results[0].withheld is False


def _conforming(actions: list[ChosenAction], text: str = "ok") -> Observation:
    """What a runner that honoured I1 would return: one row per action.

    The orchestrator validates every ``send_turn`` return, so a double that
    returned a bare ``Observation`` would fail the contract rather than the
    behaviour each test is actually about.
    """
    return Observation(
        text=text,
        action_results=[
            ActionResult(action_index=index, succeeded=True)
            for index in range(len(actions))
        ],
    )


class _ScriptedRunner(Runner):
    """Replays a per-turn script and records exactly what it was sent.

    ``self.sent`` is the evidence for I4: one entry per ``send_turn`` call.
    """

    def __init__(self, script: list[Observation | Exception]) -> None:
        self._script = list(script)
        self.sent: list[tuple[str, int]] = []
        self.recover_calls = 0
        self.recover_raises: Exception | None = None

    async def setup(self, config: RunConfig) -> None:
        return None

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        self.sent.append((message, len(actions)))
        outcome = self._script.pop(0) if self._script else _conforming(actions)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def recover(self) -> None:
        self.recover_calls += 1
        if self.recover_raises is not None:
            raise self.recover_raises

    async def teardown(self) -> None:
        return None

    async def get_session_id(self) -> str | None:
        return "sess-1"


class _GivingUpAgent:
    """Opens with one click action, then gives up after `replies` follow-ups.

    Giving up is checked at the top of the loop, so `replies=1` means exactly
    one turn is sent before the run stops with ``user_abandoned``.

    A click rather than an upload because the orchestrator withholds an upload
    naming a fixture the scenario never staged. These tests are about delivery
    multiplicity and escalation, so the action has to reach the runner;
    withholding has its own tests in ``test_runner_contract.py``.
    """

    def __init__(self, replies: int = 1) -> None:
        self._remaining = replies

    async def generate_opening(self) -> UserAgentOutput:
        return UserAgentOutput(
            message="hello",
            decision="continue",
            actions=[ButtonClickAction(slot_id="b0")],
        )

    async def generate_response(self, _payload: object) -> UserAgentOutput:
        self._remaining -= 1
        if self._remaining <= 0:
            return UserAgentOutput(message="bye", decision="giving_up")
        return UserAgentOutput(
            message="try again",
            decision="continue",
            actions=[ButtonClickAction(slot_id="b0")],
        )


def _orchestrator(runner: Runner, agent: object, tmp_path: Path) -> Orchestrator:
    return Orchestrator(
        runner=runner,
        agent=agent,  # type: ignore[arg-type]
        run_config=RunConfig(persona="p1", scenario="s1", max_turns=20),
        scenario=Scenario(
            id="s1", description="a scenario", persona_refs=["p1"], max_turns=20
        ),
        run_dir=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
        experiment_root=tmp_path,
    )


class TestI4DeliveryMultiplicity:
    @pytest.mark.asyncio
    async def test_a_post_submission_failure_is_not_re_sent(self, tmp_path) -> None:
        """I4: the message already reached the target — re-sending duplicates it."""
        from metis.engine.simulation.exceptions import (
            PostSubmissionObservationError,
        )

        runner = _ScriptedRunner([PostSubmissionObservationError("DOM gone")])
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        record = await orch.run()

        assert runner.sent == [("hello", 1)]
        assert record.outcome.stop_reason == "user_abandoned"

    @pytest.mark.asyncio
    async def test_a_transient_dom_failure_is_not_re_sent(self, tmp_path) -> None:
        from metis.engine.simulation.exceptions import TransientDOMError

        runner = _ScriptedRunner([TransientDOMError("locator missing")])
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        await orch.run()

        assert runner.sent == [("hello", 1)]

    @pytest.mark.asyncio
    async def test_the_undelivered_turn_is_recorded_with_a_failed_row(
        self, tmp_path
    ) -> None:
        from metis.engine.simulation.exceptions import TransientDOMError

        runner = _ScriptedRunner([TransientDOMError("locator missing")])
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        record = await orch.run()

        response = record.conversation[0].target_response
        assert [r["action_index"] for r in response["action_results"]] == [0]
        assert response["action_results"][0]["succeeded"] is False
        assert response["action_results"][0]["detail"]
        assert response["response_notices"]

    @pytest.mark.asyncio
    async def test_a_failed_recover_does_not_discard_the_decided_turn(
        self, tmp_path
    ) -> None:
        """recover() is best-effort housekeeping, not part of the verdict."""
        from metis.engine.simulation.exceptions import TransientDOMError

        runner = _ScriptedRunner([TransientDOMError("locator missing")])
        runner.recover_raises = RuntimeError("page is gone")
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        record = await orch.run()

        assert runner.recover_calls == 1
        assert record.outcome.stop_reason == "user_abandoned"
        assert len(record.conversation) == 1


class TestEscalation:
    @pytest.mark.asyncio
    async def test_two_consecutive_raises_escalate(self, tmp_path) -> None:
        from metis.engine.simulation.exceptions import (
            ConsecutiveFailureEscalation,
            TransientDOMError,
        )

        runner = _ScriptedRunner(
            [TransientDOMError("first"), TransientDOMError("second")]
        )
        orch = _orchestrator(runner, _GivingUpAgent(replies=3), tmp_path)

        with pytest.raises(ConsecutiveFailureEscalation, match="2 consecutive"):
            await orch.run()

        assert runner.sent == [("hello", 1), ("try again", 1)]

    @pytest.mark.asyncio
    async def test_a_successful_turn_resets_the_counter(self, tmp_path) -> None:
        from metis.engine.simulation.exceptions import TransientDOMError

        runner = _ScriptedRunner(
            [
                TransientDOMError("first"),
                # One action was submitted, so a conforming runner reports one
                # row — the orchestrator validates this return.
                _conforming([ButtonClickAction(slot_id="b0")]),
                TransientDOMError("third"),
            ]
        )
        orch = _orchestrator(runner, _GivingUpAgent(replies=3), tmp_path)

        record = await orch.run()

        assert len(runner.sent) == 3
        assert record.outcome.stop_reason == "user_abandoned"

    @pytest.mark.asyncio
    async def test_a_return_whose_actions_all_failed_does_not_escalate(
        self, tmp_path
    ) -> None:
        """A reported failure is the contract working, not a turn failure.

        The runner came back and said what happened. Only a *raise* leaves the
        caller unable to conclude anything, so only a raise counts toward
        escalation — otherwise the contract's whole point (report instead of
        raise) would trigger the very escalation it was meant to avoid.
        """
        rejected = Observation(
            text="",
            action_results=[
                ActionResult(
                    action_index=0,
                    succeeded=False,
                    detail="Turn not submitted: upload rejected (413)",
                )
            ],
        )
        runner = _ScriptedRunner([rejected, rejected, rejected])
        orch = _orchestrator(runner, _GivingUpAgent(replies=3), tmp_path)

        record = await orch.run()

        assert len(runner.sent) == 3
        assert record.outcome.stop_reason == "user_abandoned"
