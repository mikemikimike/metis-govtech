"""Demo graders on the captured Orca session (#431).

They show grader authors how to read traces through ``metis.core.trace_processing``. The LLM
demos run against a fake client, so these tests check what each grader sends and how it
handles the reply, not what a real judge would think.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from metis.core.traces import GradingInput
from metis.library.grader import JudgeArgs, LLMSettings
from metis.library.graders.demo import (
    DemoAnswerHelpfulnessGrader,
    DemoRequiredToolArgs,
    DemoRequiredToolGrader,
    DemoTaskCompletionGrader,
    DemoTraceBudgetArgs,
    DemoTraceBudgetGrader,
)
from tests.fixtures.traces import load_orca_session

if TYPE_CHECKING:
    from metis.core.grading import GradingOutput
    from metis.library.grader import Grader


def fake_client(reply: str) -> MagicMock:
    """An AsyncOpenAI stand-in whose every chat completion returns ``reply``."""
    client = MagicMock()
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
    )
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def _run(
    grader: Grader, gi: GradingInput, client: MagicMock | None = None
) -> GradingOutput:
    return asyncio.run(
        grader.grade(gi, LLMSettings(client=client or fake_client("{}")))
    )


def _prompt(client: MagicMock, call: int) -> str:
    return client.chat.completions.create.await_args_list[call].kwargs["messages"][-1][
        "content"
    ]


JUDGE = JudgeArgs(model="judge-model")


class TestRequiredTool:
    def test_required_tool_finds_make_ppt_deep_in_turn_5(self) -> None:
        out = _run(
            DemoRequiredToolGrader(DemoRequiredToolArgs(tool_name="make_ppt")),
            load_orca_session(),
        )
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 1.0)
        assert "turn 5" in result.reason
        assert "Slide_Maker.arun" in result.reason

    def test_required_tool_absent_scores_zero(self) -> None:
        out = _run(
            DemoRequiredToolGrader(DemoRequiredToolArgs(tool_name="send_email")),
            load_orca_session(),
        )
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_required_tool_never_calls_the_llm(self) -> None:
        client = fake_client("{}")
        _run(
            DemoRequiredToolGrader(DemoRequiredToolArgs(tool_name="make_ppt")),
            load_orca_session(),
            client,
        )
        client.chat.completions.create.assert_not_awaited()


class TestAnswerHelpfulness:
    def test_helpfulness_judges_each_turn_with_earlier_context(self) -> None:
        client = fake_client('{"reasoning": "ok", "score": 0.8}')
        out = _run(DemoAnswerHelpfulnessGrader(JUDGE), load_orca_session(), client)
        assert [(r.status, r.score) for r in out.results] == [("scored", 0.8)] * 5
        third = _prompt(client, 2)
        assert "## Turn 1" in third and "## Turn 3" in third
        assert "## Turn 4" not in third

    def test_the_judge_model_is_the_one_configured(self) -> None:
        client = fake_client('{"reasoning": "ok", "score": 1}')
        _run(DemoAnswerHelpfulnessGrader(JUDGE), load_orca_session(), client)
        assert (
            client.chat.completions.create.await_args_list[0].kwargs["model"]
            == "judge-model"
        )


class TestTaskCompletion:
    def test_task_completion_gives_one_result_for_the_session(self) -> None:
        client = fake_client('{"reasoning": "deck delivered", "score": 0.9}')
        out = _run(DemoTaskCompletionGrader(JUDGE), load_orca_session(), client)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.9)
        assert "## Turn 5" in _prompt(client, 0)

    def test_task_completion_says_no_file_was_checked(self) -> None:
        client = fake_client('{"reasoning": "deck delivered", "score": 0.9}')
        (result,) = _run(
            DemoTaskCompletionGrader(JUDGE), load_orca_session(), client
        ).results
        assert result.reason.endswith(
            "No file was checked: the run recorded no artifacts."
        )


def test_an_off_menu_judge_reply_is_errored() -> None:
    for reply in ("looks good", '{"reasoning": "x"}', '{"reasoning": "x", "score": 7}'):
        out = _run(
            DemoTaskCompletionGrader(JUDGE), load_orca_session(), fake_client(reply)
        )
        (result,) = out.results
        assert result.status == "errored", reply
        assert result.score is None


def test_a_failing_judge_call_is_errored() -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("rate limited"))
    (result,) = _run(
        DemoTaskCompletionGrader(JUDGE), load_orca_session(), client
    ).results
    assert result.status == "errored"
    assert "rate limited" in result.reason


def test_every_demo_skips_an_empty_session() -> None:
    graders: list[Grader] = [
        DemoTraceBudgetGrader(DemoTraceBudgetArgs()),
        DemoRequiredToolGrader(DemoRequiredToolArgs(tool_name="make_ppt")),
        DemoAnswerHelpfulnessGrader(JUDGE),
        DemoTaskCompletionGrader(JUDGE),
    ]
    for grader in graders:
        (result,) = _run(grader, GradingInput(traces=())).results
        assert result.status == "skipped", type(grader).__name__


def test_demos_produce_different_units_from_one_session() -> None:
    """#431: the same saved data, without the target or the network, yields different units."""
    gi = load_orca_session()
    client = fake_client('{"reasoning": "ok", "score": 1}')
    per_turn = _run(DemoAnswerHelpfulnessGrader(JUDGE), gi, client)
    per_session = _run(DemoTaskCompletionGrader(JUDGE), gi, client)
    assert (len(per_turn.results), len(per_session.results)) == (5, 1)


def test_demos_are_not_in_the_catalogue() -> None:
    import metis.library.graders as catalog

    assert not [name for name in vars(catalog) if name.startswith("Demo")]


def test_a_turn_the_target_crashed_on_is_judged_not_skipped() -> None:
    """No reply is the target's failure, so it is evidence to grade, never a skip (#431)."""
    from datetime import UTC, datetime

    from metis.core.traces import Observation, Trace

    crashed = Trace(
        id="t1",
        session_id="s",
        observations=(
            Observation(
                id="root",
                trace_id="t1",
                type="SPAN",
                input="help me",
                output=None,
                start_time=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
    )
    client = fake_client('{"reasoning": "no answer", "score": 0}')
    (result,) = _run(
        DemoAnswerHelpfulnessGrader(JUDGE), GradingInput(traces=(crashed,)), client
    ).results
    assert (result.status, result.score) == ("scored", 0.0)
    assert "[target error: the target returned no reply]" in _prompt(client, 0)


def test_a_turn_metis_could_not_read_is_skipped() -> None:
    from datetime import UTC, datetime

    from metis.core.traces import Observation, Trace

    unreadable = Trace(
        id="t1",
        session_id="s",
        observations=(
            Observation(
                id="root",
                trace_id="t1",
                type="SPAN",
                input={"weird": 1},
                output="an answer",
                start_time=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ),
    )
    client = fake_client('{"reasoning": "x", "score": 1}')
    (result,) = _run(
        DemoAnswerHelpfulnessGrader(JUDGE), GradingInput(traces=(unreadable,)), client
    ).results
    assert result.status == "skipped"
    client.chat.completions.create.assert_not_awaited()
