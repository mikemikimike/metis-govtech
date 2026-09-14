"""Tests for the user-agent action-section renderer, opening slots, and turn-error surfacing (#311, #315)."""

from __future__ import annotations

import pytest

from metis.engine.simulation.types import (
    ActionSlot,
    Observation,
    Persona,
    Scenario,
    UserAgentInput,
    UserAgentOutput,
)
from metis.engine.simulation.user_agent import agent as agent_module
from metis.engine.simulation.user_agent.agent import (
    UserAgent,
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
