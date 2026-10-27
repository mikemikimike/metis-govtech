"""Tests for the user-agent action-section renderer, opening slots, and turn-problem surfacing (#311, #315, #329)."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.engine.simulation.gen_1.user_agent.agent import (
    UserAgent,
    _render_artifacts,
    _render_available_actions,
    _render_observed_actions,
    _render_problems,
)
from metis.engine.simulation.gen_1.user_agent.prompts import SYSTEM_PROMPT_TEMPLATE
from metis.engine.simulation.llm_calls import LLMCallLog
from metis.engine.simulation.types import (
    ActionResult,
    ActionSlot,
    Artifact,
    Observation,
    Persona,
    Scenario,
    UserAgentInput,
    UserAgentOutput,
)

# Never written: these tests stub or skip the LLM call.
_UNUSED_LOG = LLMCallLog(Path("unused-llm_calls.jsonl"))


def test_render_available_actions_empty() -> None:
    assert _render_available_actions(None) == ""
    assert _render_available_actions([]) == ""


def test_render_available_actions_lists_slots() -> None:
    out = _render_available_actions(
        [ActionSlot(id="q1", kind="text", label="Question 1", required=True)]
    )
    assert 'id: "q1"' in out
    assert 'kind: "text"' in out
    assert "required: true" in out


def test_render_problems_empty() -> None:
    assert _render_problems([], []) == ""


def test_render_problems_lists_failed_rows_and_notices() -> None:
    out = _render_problems(
        [
            ActionResult(action_index=0, succeeded=True),
            ActionResult(
                action_index=1,
                succeeded=False,
                detail="Turn not submitted: file 'evil.exe' is not a fixture "
                "for this scenario",
                retryable=False,
            ),
        ],
        ["Response timeout — no response received"],
    )
    assert "evil.exe" in out
    assert "Response timeout — no response received" in out
    # Neutral header — problems are not only rejected uploads.
    assert "previous turn" in out.lower()


def test_render_problems_says_nothing_about_a_succeeded_action() -> None:
    out = _render_problems([ActionResult(action_index=0, succeeded=True)], [])
    assert out == ""


def test_render_problems_passes_on_the_retryable_hint() -> None:
    again = _render_problems(
        [ActionResult(action_index=0, succeeded=False, detail="x", retryable=True)], []
    )
    never = _render_problems(
        [ActionResult(action_index=0, succeeded=False, detail="x", retryable=False)], []
    )
    silent = _render_problems(
        [ActionResult(action_index=0, succeeded=False, detail="x")], []
    )
    assert again != never != silent
    assert "again" in again


def test_a_withheld_row_still_reaches_the_persona() -> None:
    """`withheld` keeps a row out of the report's blame attribution. The
    persona must still be told: an action that did not happen did not happen,
    and a persona not told proceeds believing its file was attached."""
    out = _render_problems(
        [
            ActionResult(
                action_index=0,
                succeeded=False,
                detail="Turn not submitted: file 'evil.exe' is not a fixture "
                "for this scenario",
                withheld=True,
            )
        ],
        [],
    )
    assert "evil.exe" in out


class TestTheThreeStatesAreDistinguishable:
    """The persona has no other source for what it may do next, so an absent
    block reads to it as "nothing on offer"."""

    def test_a_slot_list_renders_the_slots(self) -> None:
        out = _render_observed_actions(
            [ActionSlot(id="q1", kind="text", label="Question 1")]
        )
        assert 'id: "q1"' in out

    def test_an_empty_list_says_the_target_offers_nothing(self) -> None:
        assert _render_observed_actions([]) == (
            "\nNo actions are on offer this turn.\n"
        )

    def test_none_says_nobody_looked(self) -> None:
        assert _render_observed_actions(None) == (
            "\nThe actions on offer this turn could not be determined.\n"
        )

    def test_the_three_renderings_are_all_different(self) -> None:
        slots = _render_observed_actions([ActionSlot(id="q1", kind="text", label="Q")])
        assert (
            len({slots, _render_observed_actions([]), _render_observed_actions(None)})
            == 3
        )

    def test_a_slot_list_renders_identically_for_opening_and_response_turns(
        self,
    ) -> None:
        """One slot-line format, so a scenario's opening prompt and its
        mid-conversation prompts do not disagree about the same slot."""
        slots = [ActionSlot(id="sales.csv", kind="file_upload", label="Attach")]
        assert _render_observed_actions(slots) == _render_available_actions(slots)


def test_system_prompt_lists_persona_and_scenario_metadata_as_written() -> None:
    persona = Persona(
        id="p",
        name="p",
        description="a data analyst",
        metadata={"age": "In their fifties.", "input_style": "Terse."},
    )
    scenario = Scenario(
        id="s",
        description="upload and analyze",
        metadata={"stop_condition": "The analysis is ready."},
        persona_refs=["p"],
    )
    prompt = UserAgent(persona, scenario, llm_log=_UNUSED_LOG)._build_system_prompt()

    assert "a data analyst" in prompt
    assert "- age: In their fifties.\n- input_style: Terse." in prompt
    assert "- stop_condition: The analysis is ready." in prompt


def test_system_prompt_has_no_metadata_section_when_there_is_none() -> None:
    persona = Persona(id="p", name="p", description="a data analyst")
    scenario = Scenario(id="s", description="upload and analyze", persona_refs=["p"])
    prompt = UserAgent(persona, scenario, llm_log=_UNUSED_LOG)._build_system_prompt()

    assert "a data analyst" in prompt
    assert "More about" not in prompt


@pytest.mark.asyncio
async def test_opening_offers_fixture_upload_slots(monkeypatch) -> None:
    # The client is never called because we stub _call_llm.
    persona = Persona(id="p", name="p", description="a data analyst")
    scenario = Scenario(
        id="s",
        description="upload and analyze",
        fixtures=["sales.csv"],
        persona_refs=["p"],
    )
    ua = UserAgent(persona, scenario, llm_log=_UNUSED_LOG)

    captured: dict[str, str] = {}

    async def fake_call(prompt: str) -> UserAgentOutput:
        captured["prompt"] = prompt
        return UserAgentOutput(message="hi")

    monkeypatch.setattr(ua, "_call_llm", fake_call)
    await ua.generate_opening()

    assert "file_upload" in captured["prompt"]
    assert "sales.csv" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_response_surfaces_problems(monkeypatch) -> None:
    # The client is never called because we stub _call_llm.
    persona = Persona(id="p", name="p", description="a data analyst")
    scenario = Scenario(
        id="s",
        description="upload and analyze",
        fixtures=[],
        persona_refs=["p"],
    )
    ua = UserAgent(persona, scenario, llm_log=_UNUSED_LOG)

    captured: dict[str, str] = {}

    async def fake_call(prompt: str) -> UserAgentOutput:
        captured["prompt"] = prompt
        return UserAgentOutput(message="ok")

    monkeypatch.setattr(ua, "_call_llm", fake_call)

    payload = UserAgentInput(
        observation=Observation(
            text="Your upload was rejected.",
            action_results=[
                ActionResult(
                    action_index=0,
                    succeeded=False,
                    detail="Turn not submitted: file 'evil.exe' is not a fixture "
                    "for this scenario",
                    retryable=False,
                )
            ],
            response_notices=["The assistant's reply was cut short"],
        )
    )
    await ua.generate_response(payload)

    assert "evil.exe" in captured["prompt"]
    assert "The assistant's reply was cut short" in captured["prompt"]
    # available_actions was left at its default None: nobody looked.
    assert "could not be determined" in captured["prompt"]


def test_render_artifacts_empty() -> None:
    assert _render_artifacts(None) == ""
    assert _render_artifacts({}) == ""


def test_render_artifacts_shows_name_and_descriptions_not_uri() -> None:
    reg = {
        "abc": Artifact(
            id="abc",
            name="Q3_Sales_Merged.csv",
            path="runs/abc/Q3_Sales_Merged.csv",
            content_description="120 rows x 5 cols; Q3 total 1,234,567",
            state_description="delivered at turn 3",
            state="received",
        )
    }
    out = _render_artifacts(reg)
    assert "Q3_Sales_Merged.csv" in out
    assert "120 rows x 5 cols" in out
    assert "delivered at turn 3" in out
    assert "file://" not in out  # never leak the uri
    assert "/runs/abc/" not in out  # never leak the path


def test_agent_registry_accumulates_across_turns() -> None:
    from metis.engine.simulation.types import Observation

    agent = UserAgent(
        persona=Persona(id="p", name="p", description="a user"),
        scenario=Scenario(id="s", description="do a thing", persona_refs=["p"]),
        llm_log=_UNUSED_LOG,
    )
    a1 = Artifact(id="1", name="a.csv", content_description="rows", state="unavailable")
    a2 = Artifact(
        id="2", name="b.csv", content_description="more rows", state="unavailable"
    )
    agent._merge_artifacts(Observation(artifacts=[a1]))
    agent._merge_artifacts(Observation(artifacts=[a2, a1]))  # a1 repeated
    assert set(agent._artifacts) == {"1", "2"}


def test_render_artifacts_groups_by_source() -> None:
    from metis.core import Artifact
    from metis.engine.simulation.gen_1.user_agent.agent import _render_artifacts

    fixture = Artifact(
        name="report.txt",
        source="fixture",
        path="inputs/report.txt",
        at_turn=1,
        content_description="the input the user uploaded",
        state="received",
    )
    target = Artifact(
        name="report.txt",
        source="target",
        path="runs/out/report.txt",
        at_turn=3,
        content_description="the assistant's generated report",
        state_description="delivered at turn 3",
        state="received",
    )
    out = _render_artifacts({fixture.id: fixture, target.id: target})

    assert "Files you've uploaded" in out
    assert "Files the assistant has delivered to you" in out
    assert 'name: "report.txt" (fixture)' in out
    assert 'name: "report.txt" (delivered turn 3)' in out
    # empty registry still renders nothing
    assert _render_artifacts({}) == ""


def test_response_turn_prompt_has_artifacts_placeholder() -> None:
    from metis.engine.simulation.gen_1.user_agent.prompts import RESPONSE_TURN_PROMPT

    assert "{artifacts_section}" in RESPONSE_TURN_PROMPT


def test_turn_prompt_surfaces_described_artifact_307() -> None:
    from metis.engine.simulation.types import Artifact, Observation

    agent = UserAgent(
        persona=Persona(id="p", name="p", description="a domain expert"),
        scenario=Scenario(
            id="s", description="reconcile the sales data", persona_refs=["p"]
        ),
        llm_log=_UNUSED_LOG,
    )
    art = Artifact(
        id="art1",
        name="Q3_Sales_Merged.csv",
        path="runs/x/Q3_Sales_Merged.csv",
        content_description="2 conflicts reconciled; 120 rows; Q3 total 1,234,567",
        state_description="delivered at turn 3",
        state="received",
    )
    agent._merge_artifacts(Observation(text="Here are your files.", artifacts=[art]))
    prompt = agent._build_user_prompt(
        "Here are your files.", artifacts=agent._artifacts
    )
    assert "Q3_Sales_Merged.csv" in prompt
    assert "1,234,567" in prompt
    assert "do NOT demand" in prompt or "pasted inline" in prompt
    assert "file://" not in prompt


class TestRegistryIsAuthoritative:
    def test_rule_8_states_the_list_is_exhaustive(self) -> None:
        """Without closure the persona can believe both the list and the prose."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "every file" in rules
        assert "was not received" in rules or "did not receive" in rules
        assert "challenge" in rules

    def test_rule_8_is_not_phrased_as_a_count(self) -> None:
        """The browser runner can list one file under several ids."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "exactly" not in rules.split("## available actions")[0]

    def test_rule_8_still_forbids_demanding_inline_contents(self) -> None:
        """The original purpose of rule 8 must survive the addition."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "pasted into the chat" in rules
        assert "a real user opens the file" in rules

    def test_delivered_header_states_the_closure(self) -> None:
        artifacts = {
            # A path is what makes this a file the persona actually received;
            # path-less entries are failed downloads and are excluded below.
            "a": Artifact(
                id="a",
                name="report.txt",
                path="a/report.txt",
                content_description="A report",
                state="received",
            ),
        }
        rendered = _render_artifacts(artifacts)
        assert "every file" in rendered.lower()
        assert "report.txt" in rendered

    def test_uploaded_header_is_unchanged(self) -> None:
        """Closure applies to deliverables; the persona's own inputs are separate."""
        artifacts = {
            "a": Artifact(
                id="a", name="sales.csv", source="fixture", state="unavailable"
            ),
        }
        rendered = _render_artifacts(artifacts)
        assert "your own inputs" in rendered.lower()
        assert "every file" not in rendered.lower()

    def test_a_failed_download_is_not_listed_as_delivered(self) -> None:
        """A ``path=None`` entry under "every file you have received" is a lie.

        The runner records the failure so it stays auditable and gets retried,
        but the persona must not be able to count it toward its goal (#337).
        """
        artifacts = {
            "ok": Artifact(
                id="ok",
                name="report.txt",
                path="a/report.txt",
                content_description="A repair guide.",
                state="received",
            ),
            "bad": Artifact(
                id="bad", name="chart.vl.json", external_id="f-9", state="unfetched"
            ),
        }
        assert artifacts["bad"].state != "received"
        rendered = _render_artifacts(artifacts)
        assert "report.txt" in rendered
        assert "chart.vl.json" not in rendered
        # The failed entry's giveaway: no file means no description to render.
        assert "(no description available)" not in rendered

    def test_the_delivered_group_disappears_when_every_download_failed(self) -> None:
        """The closure header must not appear over an empty delivered list.

        And the whole section must vanish, not collapse to bare newlines: the
        filter creates a case the no-artifacts guard never saw, where the
        registry is non-empty but nothing in it is renderable.
        """
        artifacts = {
            "bad": Artifact(
                id="bad", name="chart.vl.json", external_id="f-9", state="unfetched"
            ),
        }
        assert _render_artifacts(artifacts) == ""

    def test_a_retried_download_appears_once_it_succeeds(self) -> None:
        """Exclusion is by path, not by name: the retry must still be shown."""
        artifacts = {
            "bad": Artifact(
                id="bad", name="chart.vl.json", external_id="f-9", state="unfetched"
            ),
            "good": Artifact(
                id="good",
                name="chart.vl.json",
                path="a/chart.vl.json",
                external_id="f-9",
                content_description="A bar chart of Q3 revenue.",
                state="received",
            ),
        }
        rendered = _render_artifacts(artifacts)
        assert rendered.count("chart.vl.json") == 1
        assert "A bar chart of Q3 revenue." in rendered

    def test_a_path_bearing_record_not_yet_received_is_not_delivered(self) -> None:
        """``state``, not ``path``, decides delivery.

        A runner may legitimately hold a ``path`` before ``state`` is decided
        — e.g. the Playwright runner mid-capture — so a record can carry a
        file on disk while still being ``"unfetched"``. This is the one shape
        that tells the current ``state == "received"`` filter apart from the
        old ``path is not None`` filter it replaced: the old filter would
        have wrongly counted this row as delivered.
        """
        artifacts = {
            "mid_capture": Artifact(
                id="mid_capture",
                name="chart.vl.json",
                path="tmp/chart.vl.json",
                external_id="f-9",
                state="unfetched",
            ),
        }
        assert _render_artifacts(artifacts) == ""


class TestUnresolvedDetailGuidance:
    def test_rule_8_tells_persona_to_proceed_on_best_available_info(self) -> None:
        """A description that doesn't state an exact figure must not stall the turn."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "does not settle" in rules
        assert "best information" in rules
        assert "do not ask for that same detail again" in rules

    def test_rule_8_rules_out_giving_up_over_one_unresolved_detail(self) -> None:
        """An unresolved detail alone must not end the run early."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "not grounds for giving_up on its own" in rules

    def test_rule_8_original_guarantees_survive(self) -> None:
        """The #337 closure/exhaustiveness guarantees must still hold after this addition."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "every file" in rules
        assert "pasted into the chat" in rules
        assert "a real user opens the file" in rules

    def test_rule_8_addition_stays_before_available_actions(self) -> None:
        """The new sentences belong to rule 8, not spilled past the next heading."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        before_heading = rules.split("## available actions")[0]
        assert "does not settle" in before_heading
        assert "not grounds for giving_up on its own" in before_heading

    def test_rule_8_addition_does_not_demand_fabricated_figures(self) -> None:
        """Proceeding on best-available info must not read as license to invent a number."""
        rules = SYSTEM_PROMPT_TEMPLATE.lower()
        assert "make up" not in rules
        assert "invent" not in rules
        assert "guess a" not in rules


class TestRegistryKeysOnIdentity:
    """The cumulative registry dedupes by target-side identity, not by uuid.

    ``Artifact.id`` is minted per record, so it cannot collapse two records of
    one file. Across turns that matters because a failed download is reported
    again on purpose: the runner withholds its ``fileId`` from
    ``_downloaded_file_ids`` precisely so the next turn retries it.
    """

    @staticmethod
    def _agent() -> UserAgent:
        return UserAgent(
            persona=Persona(id="p", name="p", description="a user"),
            scenario=Scenario(id="s", description="do a thing", persona_refs=["p"]),
            llm_log=_UNUSED_LOG,
        )

    def test_a_successful_retry_replaces_the_earlier_failure(self) -> None:
        """Turn 3 fails, turn 4 succeeds: one entry, holding the file."""
        from metis.engine.simulation.types import Observation

        agent = self._agent()
        failed = Artifact(
            name="chart.vl.json", external_id="f-9", at_turn=3, state="unfetched"
        )
        recovered = Artifact(
            name="chart.vl.json",
            external_id="f-9",
            path="runs/x/chart.vl.json",
            at_turn=4,
            content_description="A bar chart of Q3 revenue.",
            state="received",
        )
        assert failed.id != recovered.id  # a fresh uuid per record

        agent._merge_artifacts(Observation(artifacts=[failed]))
        agent._merge_artifacts(Observation(artifacts=[recovered]))

        assert len(agent._artifacts) == 1
        (held,) = agent._artifacts.values()
        assert held.path == "runs/x/chart.vl.json"

    def test_a_later_path_less_record_never_downgrades_a_received_file(self) -> None:
        """The reverse order must not replace a real file with a placeholder.

        Same rule :func:`reconcile_by_identity` applies within a turn: a record
        with no ``path`` loses to one that has a file, whichever arrives last.
        """
        from metis.engine.simulation.types import Observation

        agent = self._agent()
        received = Artifact(
            name="chart.vl.json",
            external_id="f-9",
            path="runs/x/chart.vl.json",
            content_description="A bar chart of Q3 revenue.",
            state="received",
        )
        stale = Artifact(name="chart.vl.json", external_id="f-9", state="unfetched")

        agent._merge_artifacts(Observation(artifacts=[received]))
        agent._merge_artifacts(Observation(artifacts=[stale]))

        assert len(agent._artifacts) == 1
        (held,) = agent._artifacts.values()
        assert held.path == "runs/x/chart.vl.json"

    def test_a_held_path_bearing_but_not_received_record_still_gets_replaced(
        self,
    ) -> None:
        """The downgrade guard keys on ``state``, not ``path``.

        A held record can carry a ``path`` without being ``"received"`` — a
        runner may hold a path mid-capture before state is decided (see
        :class:`~metis.core.artifacts.Artifact`). The old guard
        (``held.path is not None and artifact.path is None``) would have
        mistaken that for an already-received file and refused the update;
        the current guard (``held.state == "received"``) does not.
        """
        from metis.engine.simulation.types import Observation

        agent = self._agent()
        held = Artifact(
            name="chart.vl.json",
            external_id="f-9",
            path="tmp/chart.vl.json",
            state="unfetched",
        )
        later = Artifact(name="chart.vl.json", external_id="f-9", state="unavailable")

        agent._merge_artifacts(Observation(artifacts=[held]))
        agent._merge_artifacts(Observation(artifacts=[later]))

        assert len(agent._artifacts) == 1
        (kept,) = agent._artifacts.values()
        assert kept.state == "unavailable"

    def test_an_upload_and_a_deliverable_sharing_a_file_id_stay_apart(self) -> None:
        """Direction is part of the identity, because the groups render apart.

        Folding an uploaded fixture into a deliverable would relabel the
        persona's own input as something the assistant produced — under a
        header promising the list is every file it received.
        """
        from metis.engine.simulation.types import Observation

        agent = self._agent()
        uploaded = Artifact(
            name="sales.csv",
            source="fixture",
            external_id="f-up",
            path="inputs/sales.csv",
            content_description="The user's own spreadsheet.",
            state="received",
        )
        delivered = Artifact(
            name="sales.csv",
            source="target",
            external_id="f-up",
            path="runs/x/sales.csv",
            content_description="The assistant's echo of it.",
            state="received",
        )

        agent._merge_artifacts(Observation(artifacts=[uploaded, delivered]))

        assert len(agent._artifacts) == 2
        rendered = _render_artifacts(agent._artifacts)
        assert "Files you've uploaded" in rendered
        assert "Files the assistant has delivered to you" in rendered

    def test_without_an_external_id_the_uuid_is_still_the_key(self) -> None:
        """``external_id`` is optional, and without one there is nothing to
        dedupe on, so repeats occupy separate slots.

        Pinned rather than fixed: a runner that cannot name the file on the
        target's side leaves the registry no identity to reconcile, which is
        why the delivered header states absence rather than a count.
        """
        from metis.engine.simulation.types import Observation

        agent = self._agent()
        first = Artifact(
            name="report.txt", path="runs/x/report.txt", at_turn=2, state="received"
        )
        again = Artifact(
            name="report.txt", path="runs/x/report.txt", at_turn=3, state="received"
        )

        agent._merge_artifacts(Observation(artifacts=[first]))
        agent._merge_artifacts(Observation(artifacts=[again]))

        assert set(agent._artifacts) == {first.id, again.id}
