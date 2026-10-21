"""Tests for the Runner↔Observation contract enforced at the call boundary."""

from __future__ import annotations

import pytest

from metis.engine.simulation.exceptions import RunnerContractError
from metis.engine.simulation.gen_1._contract import validate_action_results
from metis.engine.simulation.types import (
    ActionResult,
    ButtonClickAction,
    ChosenAction,
    Observation,
    UserAgentInput,
)


def _actions(count: int) -> list[ChosenAction]:
    return [ButtonClickAction(slot_id=f"b{i}") for i in range(count)]


def _succeeded(count: int) -> list[ActionResult]:
    return [ActionResult(action_index=i, succeeded=True) for i in range(count)]


class TestI1Completeness:
    def test_one_ascending_row_per_action_is_accepted(self) -> None:
        validate_action_results(Observation(action_results=_succeeded(3)), _actions(3))

    def test_an_empty_action_list_needs_no_rows(self) -> None:
        validate_action_results(Observation(), [])

    def test_a_dropped_action_is_rejected(self) -> None:
        obs = Observation(action_results=_succeeded(2))
        with pytest.raises(RunnerContractError, match="2 ActionResult rows for 3"):
            validate_action_results(obs, _actions(3))

    def test_an_invented_extra_row_is_rejected(self) -> None:
        obs = Observation(action_results=_succeeded(3))
        with pytest.raises(RunnerContractError, match="3 ActionResult rows for 2"):
            validate_action_results(obs, _actions(2))

    def test_out_of_order_indices_are_rejected(self) -> None:
        obs = Observation(
            action_results=[
                ActionResult(action_index=1, succeeded=True),
                ActionResult(action_index=0, succeeded=True),
            ]
        )
        with pytest.raises(RunnerContractError, match=r"action_index is 1, expected 0"):
            validate_action_results(obs, _actions(2))

    def test_a_repeated_index_is_rejected(self) -> None:
        obs = Observation(
            action_results=[
                ActionResult(action_index=0, succeeded=True),
                ActionResult(action_index=0, succeeded=True),
            ]
        )
        with pytest.raises(RunnerContractError, match=r"expected 1"):
            validate_action_results(obs, _actions(2))


class TestWithholdingIsTheCallersVerdict:
    def test_a_runner_may_not_set_withheld(self) -> None:
        obs = Observation(
            action_results=[
                ActionResult(
                    action_index=0,
                    succeeded=False,
                    detail="I decided not to try",
                    withheld=True,
                )
            ]
        )
        with pytest.raises(RunnerContractError, match="caller's verdict"):
            validate_action_results(obs, _actions(1))


class TestI2IsNotRecheckedHere:
    def test_a_failure_with_a_detail_passes_straight_through(self) -> None:
        # I2 is enforced by ActionResult's own validators at construction
        # time. A second check here would drift from the first, so there
        # isn't one — a row with an empty detail cannot reach this function.
        obs = Observation(
            action_results=[
                ActionResult(action_index=0, succeeded=False, detail="413 rejected")
            ]
        )
        validate_action_results(obs, _actions(1))


class TestTheOrchestratorEnforcesIt:
    @pytest.mark.asyncio
    async def test_a_runner_dropping_an_action_fails_the_run(self, tmp_path) -> None:
        """A contract violation is a system error, not a retryable turn."""
        from tests.unit.engine.test_turn_recovery import (
            _GivingUpAgent,
            _orchestrator,
            _ScriptedRunner,
        )

        # The agent submits one upload action; the runner reports nothing.
        runner = _ScriptedRunner([Observation(text="here you go")])
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        with pytest.raises(RunnerContractError, match="0 ActionResult rows for 1"):
            await orch.execute()

    @pytest.mark.asyncio
    async def test_the_violation_is_not_absorbed_by_the_recovery_ladder(
        self, tmp_path
    ) -> None:
        # RunnerContractError descends straight from SimulationError
        # (exceptions.py), so it is disjoint from TurnRecoverableError,
        # ResponseTimeoutError and TrialRecoverableError — the three families
        # the ladder handles. It must escape run() untouched, and only one
        # send_turn call may have happened.
        from tests.unit.engine.test_turn_recovery import (
            _GivingUpAgent,
            _orchestrator,
            _ScriptedRunner,
        )

        runner = _ScriptedRunner([Observation(text="here you go")])
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        with pytest.raises(RunnerContractError):
            await orch.execute()
        assert len(runner.sent) == 1

    @pytest.mark.asyncio
    async def test_a_conforming_runner_completes_the_run(self, tmp_path) -> None:
        from tests.unit.engine.test_turn_recovery import (
            _GivingUpAgent,
            _orchestrator,
            _ScriptedRunner,
        )

        runner = _ScriptedRunner(
            [
                Observation(
                    text="here you go",
                    action_results=[ActionResult(action_index=0, succeeded=True)],
                )
            ]
        )
        orch = _orchestrator(runner, _GivingUpAgent(replies=1), tmp_path)

        record = await orch.execute()
        assert record.outcome.stop_reason == "user_abandoned"


class TestWithholdUnstagedUploads:
    STAGED = {"sales.csv"}
    DECLARED = {"sales.csv", "missing.csv"}

    def test_a_declared_but_absent_fixture_says_not_found(self) -> None:
        from metis.engine.simulation.gen_1._contract import withhold_unstaged_uploads
        from metis.engine.simulation.types import UploadFileAction

        _, withheld = withhold_unstaged_uploads(
            [UploadFileAction(slot_id="s", filename="missing.csv")],
            self.STAGED,
            self.DECLARED,
        )
        assert "was not found under the fixtures directory" in withheld[0].detail

    def test_an_undeclared_name_says_not_a_fixture_for_this_scenario(self) -> None:
        from metis.engine.simulation.gen_1._contract import withhold_unstaged_uploads
        from metis.engine.simulation.types import UploadFileAction

        _, withheld = withhold_unstaged_uploads(
            [UploadFileAction(slot_id="s", filename="invented.csv")],
            self.STAGED,
            self.DECLARED,
        )
        assert "is not a fixture for this scenario" in withheld[0].detail

    def test_a_staged_upload_is_forwarded_untouched(self) -> None:
        from metis.engine.simulation.gen_1._contract import withhold_unstaged_uploads
        from metis.engine.simulation.types import UploadFileAction

        action = UploadFileAction(slot_id="s", filename="sales.csv")
        forwarded, withheld = withhold_unstaged_uploads(
            [action], self.STAGED, self.DECLARED
        )
        assert forwarded == [action]
        assert withheld == []

    def test_non_upload_actions_are_never_withheld(self) -> None:
        from metis.engine.simulation.gen_1._contract import withhold_unstaged_uploads
        from metis.engine.simulation.types import ButtonClickAction, FormFillAction

        actions = [
            ButtonClickAction(slot_id="b"),
            FormFillAction(slot_id="f", value="v"),
        ]
        forwarded, withheld = withhold_unstaged_uploads(actions, set(), set())
        assert forwarded == actions
        assert withheld == []

    def test_a_withheld_row_keeps_its_original_index_and_order_survives(self) -> None:
        from metis.engine.simulation.gen_1._contract import withhold_unstaged_uploads
        from metis.engine.simulation.types import (
            ButtonClickAction,
            FormFillAction,
            UploadFileAction,
        )

        actions = [
            ButtonClickAction(slot_id="b0"),
            UploadFileAction(slot_id="s", filename="invented.csv"),
            FormFillAction(slot_id="f", value="v"),
        ]
        forwarded, withheld = withhold_unstaged_uploads(
            actions, self.STAGED, self.DECLARED
        )
        assert [a.slot_id for a in forwarded] == ["b0", "f"]
        assert [r.action_index for r in withheld] == [1]
        assert withheld[0].withheld is True
        assert withheld[0].succeeded is False


def _runner_rows(count: int) -> list[ActionResult]:
    """What a conforming runner returns for a list of length `count`."""
    return [
        ActionResult(action_index=i, succeeded=False, detail=f"runner row {i}")
        for i in range(count)
    ]


def _withheld_at(*positions: int) -> list[ActionResult]:
    return [
        ActionResult(
            action_index=p, succeeded=False, detail=f"withheld {p}", withheld=True
        )
        for p in positions
    ]


class TestMergeWithheld:
    @pytest.mark.parametrize(
        "positions, expected_withheld_at",
        [
            ((), []),
            ((0,), [0]),
            ((1,), [1]),
            ((2,), [2]),
            ((0, 1), [0, 1]),
            ((0, 2), [0, 2]),
            ((1, 2), [1, 2]),
            ((0, 1, 2), [0, 1, 2]),
        ],
    )
    def test_every_permutation_re_bases_to_a_dense_ascending_list(
        self, positions: tuple[int, ...], expected_withheld_at: list[int]
    ) -> None:
        from metis.engine.simulation.gen_1._contract import merge_withheld

        total = 3
        merged = merge_withheld(
            _runner_rows(total - len(positions)), _withheld_at(*positions)
        )
        assert [r.action_index for r in merged] == list(range(total))
        assert [i for i, r in enumerate(merged) if r.withheld] == expected_withheld_at

    def test_runner_row_order_is_preserved_around_a_gap(self) -> None:
        from metis.engine.simulation.gen_1._contract import merge_withheld

        merged = merge_withheld(_runner_rows(2), _withheld_at(1))
        assert [r.detail for r in merged] == [
            "runner row 0",
            "withheld 1",
            "runner row 1",
        ]

    def test_merging_nothing_yields_nothing(self) -> None:
        from metis.engine.simulation.gen_1._contract import merge_withheld

        assert merge_withheld([], []) == []

    def test_a_duplicate_withheld_position_is_rejected(self) -> None:
        from metis.engine.simulation.gen_1._contract import merge_withheld

        with pytest.raises(RunnerContractError, match="cannot re-base"):
            merge_withheld(_runner_rows(1), _withheld_at(0, 0))

    def test_a_withheld_position_past_the_end_is_rejected(self) -> None:
        from metis.engine.simulation.gen_1._contract import merge_withheld

        with pytest.raises(RunnerContractError, match="cannot re-base"):
            merge_withheld(_runner_rows(1), _withheld_at(5))


class TestTheWholePipeline:
    def test_one_ascending_row_per_persona_action(self) -> None:
        """withhold → send → validate → merge, end to end on the data."""
        from metis.engine.simulation.gen_1._contract import (
            merge_withheld,
            validate_action_results,
            withhold_unstaged_uploads,
        )
        from metis.engine.simulation.types import ButtonClickAction, UploadFileAction

        actions = [
            UploadFileAction(slot_id="s0", filename="invented.csv"),
            ButtonClickAction(slot_id="b"),
            UploadFileAction(slot_id="s1", filename="sales.csv"),
        ]
        forwarded, withheld = withhold_unstaged_uploads(
            actions, {"sales.csv"}, {"sales.csv"}
        )
        assert len(forwarded) == 2

        # What a conforming runner returns for the two it actually received.
        observation = Observation(action_results=_succeeded(2), available_actions=[])
        validate_action_results(observation, forwarded)

        merged = merge_withheld(observation.action_results, withheld)
        assert [r.action_index for r in merged] == [0, 1, 2]
        assert [r.withheld for r in merged] == [True, False, False]


class _UploadingAgent:
    """Opens with a single upload of `filename`, then gives up."""

    def __init__(self, filename: str) -> None:
        self._filename = filename
        self.payloads: list[UserAgentInput] = []

    async def generate_opening(self):
        from metis.engine.simulation.types import UploadFileAction, UserAgentOutput

        return UserAgentOutput(
            message="hello",
            decision="continue",
            actions=[UploadFileAction(slot_id="s0", filename=self._filename)],
        )

    async def generate_response(self, payload: UserAgentInput):
        from metis.engine.simulation.types import UserAgentOutput

        self.payloads.append(payload)
        return UserAgentOutput(message="bye", decision="giving_up")


def _withholding_orchestrator(runner, agent, tmp_path, declared: list[str]):
    from pathlib import Path

    from metis.core.trials import TrialConfig
    from metis.engine.simulation.gen_1.orchestrator import Orchestrator
    from metis.engine.simulation.types import Scenario

    fixtures_dir = Path(tmp_path) / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    return Orchestrator(
        runner=runner,
        agent=agent,  # type: ignore[arg-type]
        trial_config=TrialConfig(persona="p1", scenario="s1", fixtures=declared),
        scenario=Scenario(
            id="s1", description="a scenario", persona_refs=["p1"], max_turns=20
        ),
        run_dir=tmp_path,
        fixtures_dir=fixtures_dir,
        experiment_root=tmp_path,
    )


class TestUploadsAreWithheldByTheCaller:
    """Migrated from tests/unit/engine/test_playwright_send_turn.py.

    Those three tests pinned a check inside OrcaPlaywrightRunner.send_turn that
    this task deletes. The behaviour they protected is real and still required,
    so it moves up to the layer that now owns it — and gains coverage for the
    API runner for free, which the runner-level versions never had.
    """

    @pytest.mark.asyncio
    async def test_a_name_that_is_not_a_fixture_never_reaches_the_runner(
        self, tmp_path
    ) -> None:
        from tests.unit.engine.test_turn_recovery import _ScriptedRunner

        runner = _ScriptedRunner([Observation(text="ok")])
        agent = _UploadingAgent("evil.exe")
        orch = _withholding_orchestrator(runner, agent, tmp_path, declared=[])

        await orch.execute()

        assert runner.sent == [("hello", 0)]
        row = agent.payloads[0].observation.action_results[0]
        assert row.withheld is True
        assert "evil.exe" in row.detail
        assert "is not a fixture for this scenario" in row.detail

    @pytest.mark.asyncio
    async def test_a_declared_fixture_missing_from_disk_is_withheld(
        self, tmp_path
    ) -> None:
        from tests.unit.engine.test_turn_recovery import _ScriptedRunner

        # Declared in the run config but never written to the fixtures dir, so
        # build_fixture_artifacts skips it and it is not staged.
        runner = _ScriptedRunner([Observation(text="ok")])
        agent = _UploadingAgent("gone.csv")
        orch = _withholding_orchestrator(runner, agent, tmp_path, declared=["gone.csv"])

        await orch.execute()

        assert runner.sent == [("hello", 0)]
        row = agent.payloads[0].observation.action_results[0]
        assert row.withheld is True
        assert "was not found under the fixtures directory" in row.detail

    @pytest.mark.asyncio
    async def test_a_directory_named_like_a_fixture_is_withheld(self, tmp_path) -> None:
        from tests.unit.engine.test_turn_recovery import _ScriptedRunner

        (tmp_path / "fixtures").mkdir(exist_ok=True)
        (tmp_path / "fixtures" / "report.pdf").mkdir()

        runner = _ScriptedRunner([Observation(text="ok")])
        agent = _UploadingAgent("report.pdf")
        orch = _withholding_orchestrator(
            runner, agent, tmp_path, declared=["report.pdf"]
        )

        await orch.execute()

        assert runner.sent == [("hello", 0)]
        row = agent.payloads[0].observation.action_results[0]
        assert row.withheld is True

    @pytest.mark.asyncio
    async def test_a_staged_fixture_is_forwarded_and_not_withheld(
        self, tmp_path
    ) -> None:
        from tests.unit.engine.test_turn_recovery import _ScriptedRunner

        (tmp_path / "fixtures").mkdir(exist_ok=True)
        (tmp_path / "fixtures" / "sales.csv").write_text("a,b\n1,2\n")

        runner = _ScriptedRunner(
            [
                Observation(
                    text="got it",
                    action_results=[ActionResult(action_index=0, succeeded=True)],
                )
            ]
        )
        agent = _UploadingAgent("sales.csv")
        orch = _withholding_orchestrator(
            runner, agent, tmp_path, declared=["sales.csv"]
        )

        await orch.execute()

        assert runner.sent == [("hello", 1)]
        row = agent.payloads[0].observation.action_results[0]
        assert row.succeeded is True
        assert row.withheld is False


class TestTheLegacyChannelIsGone:
    def test_observation_has_no_errors_field(self) -> None:
        assert "errors" not in Observation.model_fields

    def test_constructing_with_errors_silently_drops_it(self) -> None:
        # `class Observation(BaseModel):` sets no model config, so Pydantic's
        # default extra="ignore" applies: an unknown keyword is dropped rather
        # than raising. Assert on the constructed object.
        obs = Observation(errors=["legacy"])  # type: ignore[call-arg]
        assert not hasattr(obs, "errors")

    def test_the_two_channels_are_the_only_problem_carriers(self) -> None:
        problem_fields = {
            name
            for name in Observation.model_fields
            if "error" in name or "notice" in name or "result" in name
        }
        assert problem_fields == {"response_notices", "action_results"}
