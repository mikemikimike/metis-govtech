"""Tests for the user-agent action-section renderer, opening slots, and turn-error surfacing (#311, #315)."""

from __future__ import annotations

import pytest

from metis.engine.simulation.types import (
    ActionSlot,
    Artifact,
    Observation,
    Persona,
    Scenario,
    UserAgentInput,
    UserAgentOutput,
)
from metis.engine.simulation.user_agent import agent as agent_module
from metis.engine.simulation.user_agent.agent import (
    UserAgent,
    _render_artifacts,
    _render_available_actions,
    _render_errors,
)


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


def test_render_errors_empty() -> None:
    assert _render_errors(None) == ""
    assert _render_errors([]) == ""


def test_render_errors_lists_each_message() -> None:
    out = _render_errors(
        [
            "Turn not submitted: file 'evil.exe' not in scenario fixtures",
            "Upload timed out after 30s",
        ]
    )
    assert "Turn not submitted: file 'evil.exe' not in scenario fixtures" in out
    assert "Upload timed out after 30s" in out
    # Neutral header — errors are not only rejected uploads.
    assert "previous turn" in out.lower()


@pytest.mark.asyncio
async def test_opening_offers_fixture_upload_slots(monkeypatch) -> None:
    # Avoid the AsyncOpenAI api_key requirement — the client is never called
    # because we stub _call_llm.
    monkeypatch.setattr(agent_module, "AsyncOpenAI", lambda **kw: object())
    persona = Persona(id="p", description="a data analyst")
    scenario = Scenario(
        id="s",
        description="upload and analyze",
        fixtures=["sales.csv"],
        persona_refs=["p"],
    )
    ua = UserAgent(persona, scenario)

    captured: dict[str, str] = {}

    async def fake_call(prompt: str) -> UserAgentOutput:
        captured["prompt"] = prompt
        return UserAgentOutput(message="hi")

    monkeypatch.setattr(ua, "_call_llm", fake_call)
    await ua.generate_opening()

    assert "file_upload" in captured["prompt"]
    assert "sales.csv" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_response_surfaces_errors(monkeypatch) -> None:
    # Stub AsyncOpenAI so no api_key is required; _call_llm is stubbed too.
    monkeypatch.setattr(agent_module, "AsyncOpenAI", lambda **kw: object())
    persona = Persona(id="p", description="a data analyst")
    scenario = Scenario(
        id="s",
        description="upload and analyze",
        fixtures=[],
        persona_refs=["p"],
    )
    ua = UserAgent(persona, scenario)

    captured: dict[str, str] = {}

    async def fake_call(prompt: str) -> UserAgentOutput:
        captured["prompt"] = prompt
        return UserAgentOutput(message="ok")

    monkeypatch.setattr(ua, "_call_llm", fake_call)

    payload = UserAgentInput(
        observation=Observation(
            text="Your upload was rejected.",
            errors=["Turn not submitted: file 'evil.exe' not in scenario fixtures"],
        )
    )
    await ua.generate_response(payload)

    assert (
        "Turn not submitted: file 'evil.exe' not in scenario fixtures"
        in captured["prompt"]
    )


def test_render_artifacts_empty() -> None:
    assert _render_artifacts(None) == ""
    assert _render_artifacts({}) == ""


def test_render_artifacts_shows_name_and_descriptions_not_uri() -> None:
    reg = {
        "abc": Artifact(
            id="abc",
            name="Q3_Sales_Merged.csv",
            uri="file:///runs/abc/Q3_Sales_Merged.csv",
            content_description="120 rows x 5 cols; Q3 total 1,234,567",
            state_description="delivered at turn 3",
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
        persona=Persona(id="p", description="a user"),
        scenario=Scenario(id="s", description="do a thing", persona_refs=["p"]),
    )
    a1 = Artifact(id="1", name="a.csv", content_description="rows")
    a2 = Artifact(id="2", name="b.csv", content_description="more rows")
    agent._merge_artifacts(Observation(artifacts=[a1]))
    agent._merge_artifacts(Observation(artifacts=[a2, a1]))  # a1 repeated
    assert set(agent._artifacts) == {"1", "2"}


def test_render_artifacts_groups_by_source() -> None:
    from metis.core import Artifact
    from metis.engine.simulation.user_agent.agent import _render_artifacts

    fixture = Artifact(
        name="report.txt",
        source="fixture",
        uri="file:///tmp/report.txt",
        at_turn=1,
        content_description="the input the user uploaded",
    )
    target = Artifact(
        name="report.txt",
        source="target",
        uri="file:///tmp/out/report.txt",
        at_turn=3,
        content_description="the assistant's generated report",
        state_description="delivered at turn 3",
    )
    out = _render_artifacts({fixture.id: fixture, target.id: target})

    assert "Files you've uploaded" in out
    assert "Files the assistant has delivered to you" in out
    assert 'name: "report.txt" (fixture)' in out
    assert 'name: "report.txt" (delivered turn 3)' in out
    # empty registry still renders nothing
    assert _render_artifacts({}) == ""


def test_response_turn_prompt_has_artifacts_placeholder() -> None:
    from metis.engine.simulation.user_agent.prompts import RESPONSE_TURN_PROMPT

    assert "{artifacts_section}" in RESPONSE_TURN_PROMPT


def test_turn_prompt_surfaces_described_artifact_307() -> None:
    from metis.engine.simulation.types import Artifact, Observation

    agent = UserAgent(
        persona=Persona(id="p", description="a domain expert"),
        scenario=Scenario(
            id="s", description="reconcile the sales data", persona_refs=["p"]
        ),
    )
    art = Artifact(
        id="art1",
        name="Q3_Sales_Merged.csv",
        uri="file:///runs/x/Q3_Sales_Merged.csv",
        content_description="2 conflicts reconciled; 120 rows; Q3 total 1,234,567",
        state_description="delivered at turn 3",
    )
    agent._merge_artifacts(Observation(text="Here are your files.", artifacts=[art]))
    prompt = agent._build_user_prompt(
        "Here are your files.", artifacts=agent._artifacts
    )
    assert "Q3_Sales_Merged.csv" in prompt
    assert "1,234,567" in prompt
    assert "do NOT demand" in prompt or "pasted inline" in prompt
    assert "file://" not in prompt
