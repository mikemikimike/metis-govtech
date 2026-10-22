"""Old tool results are shortened before each round, so a long conversation stays small (#482)."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import pytest

from metis.engine.simulation.gen_2.runners.http import trimmed
from tests.unit.engine.test_gen_2_agent_loop import (
    ScriptedLLM,
    _chat,
    _ready,
    _report,
)

if TYPE_CHECKING:
    from pathlib import Path


def _tool(result: dict[str, Any], call: str = "c") -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call, "content": json.dumps(result)}


def _assistant() -> dict[str, Any]:
    return {"role": "assistant", "content": "", "tool_calls": []}


def _body(message: dict[str, Any]) -> dict[str, Any]:
    return json.loads(message["content"])


def test_an_old_body_is_a_stub_naming_its_entry_and_the_latest_stays_whole() -> None:
    old = {"response_entry": "e7", "status": 200, "body": "x" * 1830}
    new = {"response_entry": "e9", "status": 200, "body": "latest body"}
    messages = [_assistant(), _tool(old), _assistant(), _tool(new)]

    sent = trimmed(messages)

    assert _body(sent[1]) == {
        "response_entry": "e7",
        "status": 200,
        "body": "(logged as e7, 1,830 characters)",
    }
    assert _body(sent[3]) == new


def test_every_result_of_the_latest_round_stays_whole() -> None:
    result = {"response_entry": "e1", "status": 200, "body": "b" * 50}
    messages = [_assistant(), _tool(result, "a"), _tool(result, "b")]

    assert trimmed(messages) == messages


def test_errors_and_outcomes_are_kept_whole_in_old_rounds() -> None:
    refusal = {"error": "refused, nothing was sent: forbidden"}
    files = {"listing": "e2", "files": [{"name": "a.csv", "outcome": "received"}]}
    messages = [_assistant(), _tool(refusal), _tool(files), _assistant()]

    assert trimmed(messages) == messages


def test_an_old_definition_is_a_stub_that_says_how_to_read_it_again() -> None:
    found = {"operation": "POST /orders", "definition": {"a": "b" * 2400}}
    messages = [_assistant(), _tool(found), _assistant()]

    stub = _body(trimmed(messages)[1])

    assert stub["operation"] == "POST /orders"
    assert stub["definition"].startswith("(definition of POST /orders, ")
    assert "call operation again" in stub["definition"]


def test_the_full_conversation_is_not_changed() -> None:
    old = {"response_entry": "e7", "status": 200, "body": "x" * 100}
    messages = [_assistant(), _tool(old), _assistant()]
    before = copy.deepcopy(messages)

    trimmed(messages)

    assert messages == before


@pytest.mark.asyncio
async def test_a_stubbed_result_can_still_be_cited_by_report(tmp_path: Path) -> None:
    llm = ScriptedLLM(
        [_chat()],
        [("note", {"text": "sent"})],
        [("note", {"text": "waiting"})],
    )
    runner, _ = await _ready(tmp_path, llm)
    llm._replies.append(_report(runner, 0))

    observation = await runner.act("Say ⟦hello⟧", [])

    last = llm.requests[-1]["messages"]
    chat = next(m for m in last if m["role"] == "tool")
    assert _body(chat)["body"].startswith("(logged as e")  # shortened when sent
    assert observation.reply == "hi"  # the entry still resolves
