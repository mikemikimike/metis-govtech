"""The runner agent's tool schemas and dispatcher (#481)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation.artifacts import ArtifactLedger
from metis.engine.simulation.gen_2.binding import load_target_binding
from metis.engine.simulation.gen_2.runners.http import HttpRunner, HttpRunnerFactory
from metis.engine.simulation.gen_2.runners.tools import (
    SHARED_HANDLERS,
    TOOLS,
    ActionState,
    run_tool,
)

if TYPE_CHECKING:
    from pathlib import Path

SPEC_URL = "https://app.example/openapi.json"
_BINDING = (
    f"schema_version: 1\nidentity: {{name: App}}\ntransport: http\nspec_url: {SPEC_URL}\n"
    "forbidden_calls: ['DELETE /**']\n"
)
API = "/api/v1"


class Target:
    """A fake app: a chat that lists a file, a status, a download and a broken path."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        path = request.url.path
        if path == "/openapi.json":
            return httpx.Response(200, json={"servers": [{"url": API}]})
        if path == f"{API}/chat":
            return httpx.Response(
                201,
                json={
                    "sessionId": "s-1",
                    "reply": "hi",
                    "files": [{"id": "f1", "name": "a.txt"}],
                },
            )
        if path == f"{API}/status":
            return httpx.Response(200, json={"state": "done"})
        if path == f"{API}/names":
            return httpx.Response(200, text="a.txt\nb.txt")
        if path == f"{API}/dl/f1":
            return httpx.Response(
                200, content=b"hello", headers={"content-type": "text/plain"}
            )
        if path == f"{API}/boom":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={})

    def sent(self, path: str) -> list[httpx.Request]:
        return [r for r in self.seen if r.url.path == f"{API}{path}"]


async def _ready(tmp_path: Path) -> tuple[HttpRunner, Target, ActionState]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "app.yaml").write_text(_BINDING, encoding="utf-8")
    target = Target()
    factory = HttpRunnerFactory(
        load_target_binding(inputs, "app.yaml"), transport=httpx.MockTransport(target)
    )
    await factory.start()
    trial = tmp_path / "trial"
    runner = await factory.create(trial, tmp_path, tmp_path)
    runner.use_ledger(ArtifactLedger(tmp_path, trial))
    await runner.setup(TrialConfig(persona="p", scenario="s"))
    runner.begin_action("Say ⟦hello⟧")
    return runner, target, ActionState(first_result=len(runner.results))


async def _call(
    runner: HttpRunner, state: ActionState, name: str, args: Any
) -> dict[str, Any]:
    return await run_tool(runner, state, name, json.dumps(args))


async def _chat(runner: HttpRunner, state: ActionState) -> dict[str, Any]:
    return await _call(
        runner,
        state,
        "http_request",
        {"method": "POST", "path": "/chat", "json": {"text": "{{1}}"}},
    )


def test_the_tools_are_the_seven_the_agent_may_call() -> None:
    names = {tool["function"]["name"] for tool in TOOLS}

    assert names == {
        "operation",
        "http_request",
        "poll_until",
        "fetch_files",
        "session_id_from",
        "note",
        "report",
    }
    assert all(tool["function"]["parameters"]["type"] == "object" for tool in TOOLS)


@pytest.mark.asyncio
async def test_http_request_sends_the_users_words_and_returns_the_log_entries(
    tmp_path: Path,
) -> None:
    runner, target, state = await _ready(tmp_path)

    result = await _chat(runner, state)

    assert result["status"] == 201
    assert result["response_entry"] in runner.results
    assert json.loads(target.sent("/chat")[0].content) == {"text": "hello"}


@pytest.mark.asyncio
async def test_a_refused_call_goes_back_as_an_error_and_sends_nothing(
    tmp_path: Path,
) -> None:
    runner, target, state = await _ready(tmp_path)

    result = await _call(
        runner, state, "http_request", {"method": "DELETE", "path": "/chat"}
    )

    assert result["error"].startswith("refused, nothing was sent: ")
    assert "forbidden" in result["error"]
    assert target.sent("/chat") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "raw"),
    [
        ("http_request", "{not json"),
        ("http_request", "[1, 2]"),
        ("no_such_tool", "{}"),
        ("http_request", '{"method": "GET"}'),
        ("report", '{"outcome": "done"}'),
    ],
)
async def test_bad_arguments_and_unknown_tools_are_errors_not_exceptions(
    tmp_path: Path, name: str, raw: str
) -> None:
    runner, target, state = await _ready(tmp_path)

    result = await run_tool(runner, state, name, raw)

    assert result["error"].startswith("refused, nothing was sent: ")
    assert target.sent("/chat") == []


@pytest.mark.asyncio
async def test_poll_until_takes_in_as_the_done_values(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)
    await _chat(runner, state)

    result = await _call(
        runner,
        state,
        "poll_until",
        {"path": "/status", "at": "$.state", "in": ["done"]},
    )

    assert result["condition"] == "holds"
    assert runner.open_submission is None


@pytest.mark.asyncio
async def test_poll_until_without_a_condition_is_refused(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)

    result = await _call(
        runner, state, "poll_until", {"path": "/status", "at": "$.state"}
    )

    assert "exactly one of" in result["error"]


@pytest.mark.asyncio
async def test_fetch_files_downloads_what_a_listing_names(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)
    reply = await _chat(runner, state)

    result = await _call(
        runner,
        state,
        "fetch_files",
        {
            "listing": {"entry": reply["response_entry"], "at": "$.files"},
            "id_key": "id",
            "name_key": "name",
            "download_path": "/dl/{id}",
        },
    )

    assert [f["outcome"] for f in result["files"]] == ["received"]
    assert [a.name for a in runner.ledger.artifacts()] == ["a.txt"]


@pytest.mark.asyncio
async def test_session_id_from_records_the_id_from_a_submissions_reply(
    tmp_path: Path,
) -> None:
    runner, _, state = await _ready(tmp_path)
    reply = await _chat(runner, state)
    pointer = {"entry": reply["response_entry"], "at": "$.sessionId"}

    assert "error" not in await _call(runner, state, "session_id_from", pointer)

    assert runner.session_id == "s-1"


@pytest.mark.asyncio
async def test_session_id_from_refuses_an_earlier_actions_non_submission_result(
    tmp_path: Path,
) -> None:
    runner, _, state = await _ready(tmp_path)
    await _chat(runner, state)
    status = await _call(
        runner, state, "http_request", {"method": "GET", "path": "/status"}
    )
    runner.begin_action("Say ⟦more⟧")

    result = await _call(
        runner,
        state,
        "session_id_from",
        {"entry": status["response_entry"], "at": "$.state"},
    )

    assert result["error"].startswith("refused, nothing was sent: ")
    assert runner.session_id is None


@pytest.mark.asyncio
async def test_note_keeps_what_the_agent_learned(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)

    await _call(runner, state, "note", {"text": "the target wants JSON"})

    assert runner.notes == ["the target wants JSON"]


@pytest.mark.asyncio
async def test_report_resolves_the_reply_and_keeps_the_reading_apart(
    tmp_path: Path,
) -> None:
    runner, _, state = await _ready(tmp_path)
    reply = await _chat(runner, state)

    result = await _call(
        runner,
        state,
        "report",
        {
            "outcome": "done",
            "why": "sent it",
            "next_options": "ask more",
            "reply_from": {"entry": reply["response_entry"], "at": "$.reply"},
            "promised": [{"entry": reply["response_entry"], "at": "$.files[0].name"}],
        },
    )

    assert "error" not in result
    assert state.report is not None
    assert state.report.reply == "hi"
    assert state.report.promised == ["a.txt"]
    assert (state.report.reading.outcome, state.report.reading.why) == (
        "done",
        "sent it",
    )
    assert state.report.reading.next_options == "ask more"


@pytest.mark.asyncio
async def test_a_reply_cited_from_an_earlier_action_is_refused(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)
    earlier = await _chat(runner, state)
    runner.begin_action("Say ⟦again⟧")
    state = ActionState(first_result=len(runner.results))

    result = await _call(
        runner,
        state,
        "report",
        {
            "outcome": "done",
            "why": "x",
            "reply_from": {"entry": earlier["response_entry"], "at": "$.reply"},
        },
    )

    assert "not one of the entries you may cite" in result["error"]
    assert state.report is None


@pytest.mark.asyncio
async def test_a_promised_name_must_be_a_single_line(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)
    names = await _call(
        runner, state, "http_request", {"method": "GET", "path": "/names"}
    )

    result = await _call(
        runner,
        state,
        "report",
        {
            "outcome": "partial",
            "why": "x",
            "promised": [{"entry": names["response_entry"]}],
        },
    )

    assert "single line" in result["error"]
    assert state.report is None


@pytest.mark.asyncio
async def test_a_transport_failure_is_an_error_and_is_remembered(
    tmp_path: Path,
) -> None:
    runner, _, state = await _ready(tmp_path)

    result = await _call(
        runner, state, "http_request", {"method": "GET", "path": "/boom"}
    )

    assert "error" in result
    assert state.transport_failed is True


@pytest.mark.asyncio
async def test_run_tool_uses_the_handlers_it_is_given(tmp_path: Path) -> None:
    runner, _, state = await _ready(tmp_path)

    async def ping(_runner: Any, _state: ActionState, args: dict[str, Any]) -> Any:
        return {"pong": args}

    given = await run_tool(runner, state, "ping", '{"a": 1}', {"ping": ping})
    default = await run_tool(runner, state, "ping", "{}")

    assert given == {"pong": {"a": 1}}
    assert default["error"].startswith("refused, nothing was sent: there is no tool")


def test_the_handlers_any_runner_can_share() -> None:
    assert set(SHARED_HANDLERS) == {"session_id_from", "note", "report"}
