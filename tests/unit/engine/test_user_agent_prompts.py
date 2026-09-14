"""Tests for the user-agent action-section renderer and opening slots (#311)."""

from __future__ import annotations

import pytest

from metis.engine.simulation.types import (
    ActionSlot,
    Persona,
    Scenario,
    UserAgentOutput,
)
from metis.engine.simulation.user_agent import agent as agent_module
from metis.engine.simulation.user_agent.agent import (
    UserAgent,
    _render_available_actions,
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
