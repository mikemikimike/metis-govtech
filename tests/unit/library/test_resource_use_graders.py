"""The Resource Use graders: deterministic, session-scoped, no judge call.

Each grader computes a measured value from trace data and scores 1.0 when the value is within
the user's budget, 0.0 when it is over. The measured value is in the reason text.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from metis.core.grading import GradingOutput
from metis.core.traces import GradingInput, Observation, Trace
from metis.library.grader import LLMSettings
from metis.library.graders.resource_use import (
    ElapsedTimeGrader,
    ExecutionStepCountGrader,
    ModelCallCountGrader,
    MonetaryCostGrader,
    TokenUsageGrader,
    ToolCallCountGrader,
)
from metis.library.graders.resource_use._elapsed_time import ElapsedTimeArgs
from metis.library.graders.resource_use._execution_step_count import (
    ExecutionStepCountArgs,
)
from metis.library.graders.resource_use._model_call_count import ModelCallCountArgs
from metis.library.graders.resource_use._monetary_cost import MonetaryCostArgs
from metis.library.graders.resource_use._token_usage import TokenUsageArgs
from metis.library.graders.resource_use._tool_call_count import ToolCallCountArgs
from metis.library.taxonomy import (
    Aggregation,
    GraderType,
    JudgmentForm,
    Measure,
    ReferenceType,
    Scope,
)
from tests.fixtures.criterion_judge import judge_client


def _t(second: int) -> datetime:
    return datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC)


def _obs(trace_id: str, obs_id: str, second: int, **fields: object) -> Observation:
    return Observation(id=obs_id, trace_id=trace_id, start_time=_t(second), **fields)  # type: ignore[arg-type]


def _gen_obs_with_usage(
    trace_id: str, obs_id: str, second: int, **raw_extras: object
) -> Observation:
    row: dict[str, object] = {
        "id": obs_id,
        "traceId": trace_id,
        "startTime": _t(second).isoformat(),
        "type": "GENERATION",
        "parentObservationId": f"{trace_id}-root",
    }
    row.update(raw_extras)
    return Observation.model_validate(row)


def _turn_trace(
    trace_id: str,
    start: int,
    end: int,
    *extra: Observation,
) -> Trace:
    root = Observation(
        id=f"{trace_id}-root",
        trace_id=trace_id,
        type="SPAN",
        input="q",
        output="a",
        start_time=_t(start),
        end_time=_t(end),
    )
    return Trace(id=trace_id, session_id="s", observations=(root, *extra))


def _run(
    grader: object, gi: GradingInput
) -> tuple[GradingOutput, list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []
    client = judge_client(
        json.dumps({"status": "scored", "score": 1, "reason": "ok"}), requests
    )

    async def run() -> GradingOutput:
        async with client:
            return await grader.grade(gi, LLMSettings(client))  # type: ignore[union-attr]

    return asyncio.run(run()), requests


EMPTY = GradingInput(traces=())


# ---------------------------------------------------------------------------
# Taxonomy declarations
# ---------------------------------------------------------------------------


class TestTaxonomy:
    def test_token_usage_taxonomy(self) -> None:
        t = TokenUsageGrader.taxonomy
        assert t.measure is Measure.TOKEN_USAGE
        assert t.scopes == (Scope.SESSION,)
        assert t.grader_types == (GraderType.DETERMINISTIC,)
        assert t.reference_types == (ReferenceType.POLICY_RULE,)
        assert t.judgment_forms == (JudgmentForm.BINARY,)
        assert t.aggregations == (Aggregation.NONE_SINGLE_SCORE,)

    def test_elapsed_time_taxonomy(self) -> None:
        assert ElapsedTimeGrader.taxonomy.measure is Measure.ELAPSED_TIME

    def test_model_call_count_taxonomy(self) -> None:
        assert ModelCallCountGrader.taxonomy.measure is Measure.MODEL_CALL_COUNT

    def test_tool_call_count_taxonomy(self) -> None:
        assert ToolCallCountGrader.taxonomy.measure is Measure.TOOL_CALL_COUNT

    def test_monetary_cost_taxonomy(self) -> None:
        assert MonetaryCostGrader.taxonomy.measure is Measure.MONETARY_COST

    def test_execution_step_count_taxonomy(self) -> None:
        assert ExecutionStepCountGrader.taxonomy.measure is Measure.EXECUTION_STEP_COUNT


# ---------------------------------------------------------------------------
# ElapsedTimeGrader
# ---------------------------------------------------------------------------


class TestElapsedTime:
    def test_within_budget_scores_one(self) -> None:
        gi = GradingInput(traces=(_turn_trace("t1", 0, 5),))
        grader = ElapsedTimeGrader(ElapsedTimeArgs(max_seconds=10.0))
        out, requests = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "session")
        assert "5.0 second(s)" in result.reason
        assert requests == []

    def test_over_budget_scores_zero(self) -> None:
        gi = GradingInput(traces=(_turn_trace("t1", 0, 20),))
        grader = ElapsedTimeGrader(ElapsedTimeArgs(max_seconds=10.0))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_empty_session_is_errored(self) -> None:
        grader = ElapsedTimeGrader(ElapsedTimeArgs(max_seconds=10.0))
        out, requests = _run(grader, EMPTY)
        (result,) = out.results
        assert result.status == "errored"
        assert requests == []


# ---------------------------------------------------------------------------
# ModelCallCountGrader
# ---------------------------------------------------------------------------


class TestModelCallCount:
    def test_within_budget_scores_one(self) -> None:
        gen = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = ModelCallCountGrader(ModelCallCountArgs(max_calls=5))
        out, requests = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "session")
        assert "1 model call(s)" in result.reason
        assert requests == []

    def test_over_budget_scores_zero(self) -> None:
        gen1 = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        gen2 = _obs("t1", "g2", 2, type="GENERATION", parent_observation_id="t1-root")
        gen3 = _obs("t1", "g3", 3, type="GENERATION", parent_observation_id="t1-root")
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen1, gen2, gen3),))
        grader = ModelCallCountGrader(ModelCallCountArgs(max_calls=2))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_empty_session_is_errored(self) -> None:
        grader = ModelCallCountGrader(ModelCallCountArgs(max_calls=5))
        out, _ = _run(grader, EMPTY)
        (result,) = out.results
        assert result.status == "errored"


# ---------------------------------------------------------------------------
# ToolCallCountGrader
# ---------------------------------------------------------------------------


class TestToolCallCount:
    def test_within_budget_scores_one(self) -> None:
        tool = _obs(
            "t1", "tc1", 1, type="TOOL", name="search", parent_observation_id="t1-root"
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, tool),))
        grader = ToolCallCountGrader(ToolCallCountArgs(max_calls=5))
        out, requests = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "session")
        assert "1 tool call(s)" in result.reason
        assert requests == []

    def test_over_budget_scores_zero(self) -> None:
        t1 = _obs(
            "t1", "tc1", 1, type="TOOL", name="a", parent_observation_id="t1-root"
        )
        t2 = _obs(
            "t1", "tc2", 2, type="TOOL", name="b", parent_observation_id="t1-root"
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, t1, t2),))
        grader = ToolCallCountGrader(ToolCallCountArgs(max_calls=1))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_empty_session_is_errored(self) -> None:
        grader = ToolCallCountGrader(ToolCallCountArgs(max_calls=5))
        out, _ = _run(grader, EMPTY)
        (result,) = out.results
        assert result.status == "errored"


# ---------------------------------------------------------------------------
# ExecutionStepCountGrader
# ---------------------------------------------------------------------------


class TestExecutionStepCount:
    def test_within_budget_scores_one(self) -> None:
        gen = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        tool = _obs(
            "t1", "tc1", 2, type="TOOL", name="run", parent_observation_id="t1-root"
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen, tool),))
        grader = ExecutionStepCountGrader(ExecutionStepCountArgs(max_steps=5))
        out, requests = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "session")
        assert "2 execution step(s)" in result.reason
        assert requests == []

    def test_over_budget_scores_zero(self) -> None:
        gen = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        tool = _obs(
            "t1", "tc1", 2, type="TOOL", name="run", parent_observation_id="t1-root"
        )
        agent = _obs(
            "t1", "a1", 3, type="AGENT", name="Sub", parent_observation_id="t1-root"
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen, tool, agent),))
        grader = ExecutionStepCountGrader(ExecutionStepCountArgs(max_steps=2))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_empty_session_is_errored(self) -> None:
        grader = ExecutionStepCountGrader(ExecutionStepCountArgs(max_steps=5))
        out, _ = _run(grader, EMPTY)
        (result,) = out.results
        assert result.status == "errored"


# ---------------------------------------------------------------------------
# TokenUsageGrader
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_within_budget_scores_one(self) -> None:
        gen = _gen_obs_with_usage(
            "t1",
            "g1",
            1,
            usageDetails={"input": 100, "output": 50, "total": 150},
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = TokenUsageGrader(TokenUsageArgs(max_total_tokens=200))
        out, requests = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "session")
        assert "150" in result.reason
        assert requests == []

    def test_over_budget_scores_zero(self) -> None:
        gen = _gen_obs_with_usage(
            "t1",
            "g1",
            1,
            usageDetails={"input": 500, "output": 600, "total": 1100},
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = TokenUsageGrader(TokenUsageArgs(max_total_tokens=1000))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_input_category(self) -> None:
        gen = _gen_obs_with_usage(
            "t1",
            "g1",
            1,
            usageDetails={"input": 100, "output": 50, "total": 150},
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = TokenUsageGrader(
            TokenUsageArgs(max_total_tokens=200, token_category="input")
        )
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert result.score == 1.0
        assert "100" in result.reason
        assert "input" in result.reason

    def test_missing_usage_data_is_errored(self) -> None:
        gen = _gen_obs_with_usage("t1", "g1", 1)
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = TokenUsageGrader(TokenUsageArgs(max_total_tokens=1000))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert result.status == "errored"

    def test_empty_session_is_errored(self) -> None:
        grader = TokenUsageGrader(TokenUsageArgs(max_total_tokens=1000))
        out, _ = _run(grader, EMPTY)
        (result,) = out.results
        assert result.status == "errored"


# ---------------------------------------------------------------------------
# MonetaryCostGrader
# ---------------------------------------------------------------------------


class TestMonetaryCost:
    def test_within_budget_scores_one(self) -> None:
        gen = _gen_obs_with_usage(
            "t1",
            "g1",
            1,
            costDetails={"input": 0.001, "output": 0.002, "total": 0.003},
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = MonetaryCostGrader(MonetaryCostArgs(max_cost=0.01))
        out, requests = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "session")
        assert "USD" in result.reason
        assert requests == []

    def test_over_budget_scores_zero(self) -> None:
        gen = _gen_obs_with_usage(
            "t1",
            "g1",
            1,
            costDetails={"total": 0.05},
        )
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = MonetaryCostGrader(MonetaryCostArgs(max_cost=0.01))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert (result.status, result.score) == ("scored", 0.0)

    def test_missing_cost_data_is_errored(self) -> None:
        gen = _gen_obs_with_usage("t1", "g1", 1)
        gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen),))
        grader = MonetaryCostGrader(MonetaryCostArgs(max_cost=1.0))
        out, _ = _run(grader, gi)
        (result,) = out.results
        assert result.status == "errored"

    def test_empty_session_is_errored(self) -> None:
        grader = MonetaryCostGrader(MonetaryCostArgs(max_cost=1.0))
        out, _ = _run(grader, EMPTY)
        (result,) = out.results
        assert result.status == "errored"


# ---------------------------------------------------------------------------
# No judge calls
# ---------------------------------------------------------------------------


def test_no_grader_makes_judge_calls() -> None:
    gen = _gen_obs_with_usage(
        "t1",
        "g1",
        1,
        usageDetails={"input": 10, "output": 5, "total": 15},
        costDetails={"total": 0.001},
    )
    tool = _obs(
        "t1", "tc1", 2, type="TOOL", name="run", parent_observation_id="t1-root"
    )
    gi = GradingInput(traces=(_turn_trace("t1", 0, 10, gen, tool),))
    graders = [
        ElapsedTimeGrader(ElapsedTimeArgs(max_seconds=100.0)),
        ModelCallCountGrader(ModelCallCountArgs(max_calls=100)),
        ToolCallCountGrader(ToolCallCountArgs(max_calls=100)),
        ExecutionStepCountGrader(ExecutionStepCountArgs(max_steps=100)),
        TokenUsageGrader(TokenUsageArgs(max_total_tokens=100)),
        MonetaryCostGrader(MonetaryCostArgs(max_cost=1.0)),
    ]
    for grader in graders:
        _, requests = _run(grader, gi)
        assert requests == [], type(grader).__name__
