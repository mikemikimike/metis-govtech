"""The criterion judge grades recorded evidence and reports model failures."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from metis.core.artifacts import Artifact
from metis.core.traces import GradingInput
from metis.library.grader import LLMSettings
from metis.library.graders import CriterionJudgeGrader
from metis.library.graders._criterion_judge import CriterionJudgeArgs
from tests.fixtures.criterion_judge import judge_client, recorded_session


@pytest.mark.parametrize(
    ("reply", "status", "score"),
    [
        (
            {"status": "scored", "score": 1, "reason": "The source is named."},
            "scored",
            1,
        ),
        (
            {
                "status": "scored",
                "score": 0,
                "reason": "The required citation is absent.",
            },
            "scored",
            0,
        ),
        (
            {
                "status": "skipped",
                "score": None,
                "reason": "The condition did not occur.",
            },
            "skipped",
            None,
        ),
        ({"status": "scored", "score": 0.5, "reason": "Partial."}, "errored", None),
        ({"status": "scored", "score": True, "reason": "Yes."}, "errored", None),
        ({"status": "scored", "score": "1", "reason": "Yes."}, "errored", None),
        ({"status": "skipped", "score": 1, "reason": "No."}, "errored", None),
        ({"status": "scored", "score": 1, "reason": " "}, "errored", None),
        ("not json", "errored", None),
        ("", "errored", None),
    ],
)
def test_response_contract_and_recorded_evidence(reply, status, score) -> None:
    requests = []
    client = judge_client(
        reply if isinstance(reply, str) else json.dumps(reply), requests
    )
    grader = CriterionJudgeGrader(
        CriterionJudgeArgs(model="test-judge", criterion="Name a source.")
    )

    async def run():
        async with client:
            return await grader.grade(recorded_session(), LLMSettings(client))

    [result] = asyncio.run(run()).results
    assert (result.status, result.score) == (status, score)
    assert result.reason.strip()
    [request] = requests
    assert request["model"] == "test-judge"
    assert "Name a source." in request["messages"][0]["content"]
    observations = json.loads(request["messages"][1]["content"])[0]["observations"]
    assert [o["id"] for o in observations] == ["root", "tool"]
    assert observations[1]["output"] == {"url": "example.org"}


def test_provider_failure_is_an_error() -> None:
    requests = []
    client = judge_client("unavailable", requests, status_code=503)
    grader = CriterionJudgeGrader(
        CriterionJudgeArgs(model="test-judge", criterion="Name a source.")
    )

    async def run():
        async with client:
            return await grader.grade(recorded_session(), LLMSettings(client))

    [result] = asyncio.run(run()).results
    assert result.status == "errored"
    assert result.score is None
    assert len(requests) == 1


@pytest.mark.parametrize(
    "artifacts",
    [
        (),
        (
            Artifact(
                name="answer.txt",
                source="target",
                state="received",
                path="/unread/answer.txt",
            ),
        ),
    ],
)
def test_empty_session_skips_without_a_model_call(artifacts) -> None:
    requests = []
    client = judge_client("unused", requests)
    grader = CriterionJudgeGrader(
        CriterionJudgeArgs(model="test-judge", criterion="Name a source.")
    )

    async def run():
        async with client:
            return await grader.grade(
                GradingInput(traces=(), artifacts=artifacts), LLMSettings(client)
            )

    assert asyncio.run(run()).results[0].status == "skipped"
    assert requests == []


def test_runtime_instructions_must_be_nonempty() -> None:
    with pytest.raises(ValidationError, match="criterion"):
        CriterionJudgeArgs(model="test-judge", criterion=" ")


@pytest.mark.parametrize(
    ("finish_reason", "refusal"),
    [("length", None), ("stop", "Cannot assess this request.")],
)
def test_incomplete_or_refused_assessment_is_an_error(finish_reason, refusal) -> None:
    requests = []
    client = judge_client(
        '{"status":"scored","score":1,"reason":"Yes."}',
        requests,
        finish_reason=finish_reason,
        refusal=refusal,
    )
    grader = CriterionJudgeGrader(
        CriterionJudgeArgs(model="test-judge", criterion="Name a source.")
    )

    async def run():
        async with client:
            return await grader.grade(recorded_session(), LLMSettings(client))

    assert asyncio.run(run()).results[0].status == "errored"
