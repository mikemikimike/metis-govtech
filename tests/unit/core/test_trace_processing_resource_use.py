"""The trace processor's resource-use helpers.

Each helper reads one aggregate quantity from the session's traces: counts of observations by
type, elapsed wall-clock time, token usage from ``usageDetails``, and monetary cost from
``costDetails``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from metis.core.trace_processing import (
    Problem,
    execution_step_count,
    generation_count,
    session_cost,
    session_elapsed_seconds,
    token_usage,
    tool_call_count,
)
from metis.core.traces import Observation, Trace


def _t(second: int) -> datetime:
    return datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC)


def _obs(trace_id: str, obs_id: str, second: int, **fields: object) -> Observation:
    return Observation(id=obs_id, trace_id=trace_id, start_time=_t(second), **fields)  # type: ignore[arg-type]


def _gen_obs(
    trace_id: str, obs_id: str, second: int, **raw_extras: object
) -> Observation:
    """A GENERATION observation built via model_validate so extra keys land in ``raw``."""
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
    user: object = "q",
    reply: object = "a",
) -> Trace:
    root = Observation(
        id=f"{trace_id}-root",
        trace_id=trace_id,
        type="SPAN",
        input=user,
        output=reply,
        start_time=_t(start),
        end_time=_t(end),
    )
    return Trace(id=trace_id, session_id="s", observations=(root, *extra))


# ---------------------------------------------------------------------------
# generation_count
# ---------------------------------------------------------------------------


class TestGenerationCount:
    def test_counts_generation_observations(self) -> None:
        gen1 = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        gen2 = _obs("t1", "g2", 2, type="GENERATION", parent_observation_id="t1-root")
        traces = (_turn_trace("t1", 0, 10, gen1, gen2),)
        assert generation_count(traces) == 2

    def test_ignores_non_generation_types(self) -> None:
        tool = _obs("t1", "tool1", 1, type="TOOL", parent_observation_id="t1-root")
        span = _obs("t1", "span1", 2, type="SPAN", parent_observation_id="t1-root")
        agent = _obs("t1", "agent1", 3, type="AGENT", parent_observation_id="t1-root")
        traces = (_turn_trace("t1", 0, 10, tool, span, agent),)
        assert generation_count(traces) == 0

    def test_counts_across_multiple_traces(self) -> None:
        g1 = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        g2 = _obs("t2", "g2", 6, type="GENERATION", parent_observation_id="t2-root")
        traces = (_turn_trace("t1", 0, 5, g1), _turn_trace("t2", 5, 10, g2))
        assert generation_count(traces) == 2

    def test_empty_traces_returns_zero(self) -> None:
        assert generation_count(()) == 0

    def test_no_generations_returns_zero(self) -> None:
        traces = (_turn_trace("t1", 0, 10),)
        assert generation_count(traces) == 0


# ---------------------------------------------------------------------------
# tool_call_count
# ---------------------------------------------------------------------------


class TestToolCallCount:
    def test_counts_tool_observations(self) -> None:
        t1 = _obs(
            "t1", "tc1", 1, type="TOOL", name="search", parent_observation_id="t1-root"
        )
        t2 = _obs(
            "t1", "tc2", 2, type="TOOL", name="write", parent_observation_id="t1-root"
        )
        traces = (_turn_trace("t1", 0, 10, t1, t2),)
        assert tool_call_count(traces) == 2

    def test_counts_failed_tool_calls(self) -> None:
        ok = _obs(
            "t1", "tc1", 1, type="TOOL", name="search", parent_observation_id="t1-root"
        )
        err = _obs(
            "t1",
            "tc2",
            2,
            type="TOOL",
            name="write",
            level="ERROR",
            status_message="timeout",
            parent_observation_id="t1-root",
        )
        traces = (_turn_trace("t1", 0, 10, ok, err),)
        assert tool_call_count(traces) == 2

    def test_empty_traces_returns_zero(self) -> None:
        assert tool_call_count(()) == 0

    def test_no_tools_returns_zero(self) -> None:
        gen = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        traces = (_turn_trace("t1", 0, 10, gen),)
        assert tool_call_count(traces) == 0


# ---------------------------------------------------------------------------
# session_elapsed_seconds
# ---------------------------------------------------------------------------


class TestSessionElapsedSeconds:
    def test_single_trace_uses_root_start_and_end(self) -> None:
        traces = (_turn_trace("t1", 0, 10),)
        assert session_elapsed_seconds(traces) == 10.0

    def test_multiple_traces_first_start_to_last_end(self) -> None:
        traces = (_turn_trace("t1", 0, 5), _turn_trace("t2", 5, 30))
        assert session_elapsed_seconds(traces) == 30.0

    def test_empty_traces_is_a_problem(self) -> None:
        result = session_elapsed_seconds(())
        assert isinstance(result, Problem)
        assert result.kind == "missing"

    def test_missing_start_time_is_a_problem(self) -> None:
        root = Observation(
            id="r",
            trace_id="t1",
            type="SPAN",
            input="q",
            output="a",
            end_time=_t(10),
        )
        traces = (Trace(id="t1", session_id="s", observations=(root,)),)
        result = session_elapsed_seconds(traces)
        assert isinstance(result, Problem)
        assert "start time" in result.detail

    def test_missing_end_time_is_a_problem(self) -> None:
        root = Observation(
            id="r",
            trace_id="t1",
            type="SPAN",
            input="q",
            output="a",
            start_time=_t(0),
        )
        traces = (Trace(id="t1", session_id="s", observations=(root,)),)
        result = session_elapsed_seconds(traces)
        assert isinstance(result, Problem)
        assert "end time" in result.detail


# ---------------------------------------------------------------------------
# execution_step_count
# ---------------------------------------------------------------------------


class TestExecutionStepCount:
    def test_counts_generation_tool_and_agent(self) -> None:
        gen = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        tool = _obs(
            "t1", "tc1", 2, type="TOOL", name="search", parent_observation_id="t1-root"
        )
        agent = _obs(
            "t1", "a1", 3, type="AGENT", name="Sub", parent_observation_id="t1-root"
        )
        traces = (_turn_trace("t1", 0, 10, gen, tool, agent),)
        assert execution_step_count(traces) == 3

    def test_excludes_root_observation(self) -> None:
        traces = (_turn_trace("t1", 0, 10),)
        assert execution_step_count(traces) == 0

    def test_excludes_span_observations(self) -> None:
        span = _obs("t1", "s1", 1, type="SPAN", parent_observation_id="t1-root")
        traces = (_turn_trace("t1", 0, 10, span),)
        assert execution_step_count(traces) == 0

    def test_empty_traces_returns_zero(self) -> None:
        assert execution_step_count(()) == 0

    def test_counts_across_multiple_traces(self) -> None:
        gen = _obs("t1", "g1", 1, type="GENERATION", parent_observation_id="t1-root")
        tool = _obs(
            "t2", "tc1", 6, type="TOOL", name="run", parent_observation_id="t2-root"
        )
        traces = (_turn_trace("t1", 0, 5, gen), _turn_trace("t2", 5, 10, tool))
        assert execution_step_count(traces) == 2


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_sums_usage_details_across_generations(self) -> None:
        g1 = _gen_obs(
            "t1", "g1", 1, usageDetails={"input": 100, "output": 50, "total": 150}
        )
        g2 = _gen_obs(
            "t1", "g2", 2, usageDetails={"input": 200, "output": 80, "total": 280}
        )
        traces = (_turn_trace("t1", 0, 10, g1, g2),)
        result = token_usage(traces)
        assert result == {"input": 300, "output": 130, "total": 430}

    def test_skips_observations_without_usage_details(self) -> None:
        g1 = _gen_obs(
            "t1", "g1", 1, usageDetails={"input": 100, "output": 50, "total": 150}
        )
        g2 = _gen_obs("t1", "g2", 2)
        traces = (_turn_trace("t1", 0, 10, g1, g2),)
        result = token_usage(traces)
        assert result == {"input": 100, "output": 50, "total": 150}

    def test_no_usage_data_is_a_problem(self) -> None:
        g1 = _gen_obs("t1", "g1", 1)
        traces = (_turn_trace("t1", 0, 10, g1),)
        result = token_usage(traces)
        assert isinstance(result, Problem)
        assert result.kind == "missing"

    def test_empty_traces_is_a_problem(self) -> None:
        result = token_usage(())
        assert isinstance(result, Problem)
        assert result.kind == "missing"

    def test_ignores_non_generation_observations(self) -> None:
        tool = Observation.model_validate(
            {
                "id": "tc1",
                "traceId": "t1",
                "startTime": _t(1).isoformat(),
                "type": "TOOL",
                "parentObservationId": "t1-root",
                "usageDetails": {"input": 999, "output": 999, "total": 1998},
            }
        )
        traces = (_turn_trace("t1", 0, 10, tool),)
        result = token_usage(traces)
        assert isinstance(result, Problem)

    def test_skips_non_integer_values_in_usage_details(self) -> None:
        g1 = _gen_obs(
            "t1", "g1", 1, usageDetails={"input": 100, "bad": "not_int", "total": 100}
        )
        traces = (_turn_trace("t1", 0, 10, g1),)
        result = token_usage(traces)
        assert result == {"input": 100, "total": 100}

    def test_sums_across_multiple_traces(self) -> None:
        g1 = _gen_obs(
            "t1", "g1", 1, usageDetails={"input": 50, "output": 20, "total": 70}
        )
        g2 = _gen_obs(
            "t2", "g2", 6, usageDetails={"input": 30, "output": 10, "total": 40}
        )
        traces = (_turn_trace("t1", 0, 5, g1), _turn_trace("t2", 5, 10, g2))
        result = token_usage(traces)
        assert result == {"input": 80, "output": 30, "total": 110}


# ---------------------------------------------------------------------------
# session_cost
# ---------------------------------------------------------------------------


class TestSessionCost:
    def test_sums_cost_details_total(self) -> None:
        g1 = _gen_obs(
            "t1", "g1", 1, costDetails={"input": 0.001, "output": 0.002, "total": 0.003}
        )
        g2 = _gen_obs(
            "t1", "g2", 2, costDetails={"input": 0.004, "output": 0.005, "total": 0.009}
        )
        traces = (_turn_trace("t1", 0, 10, g1, g2),)
        result = session_cost(traces)
        assert isinstance(result, float)
        assert abs(result - 0.012) < 1e-9

    def test_falls_back_to_calculated_total_cost(self) -> None:
        g1 = _gen_obs("t1", "g1", 1, calculatedTotalCost=0.005)
        traces = (_turn_trace("t1", 0, 10, g1),)
        result = session_cost(traces)
        assert isinstance(result, float)
        assert abs(result - 0.005) < 1e-9

    def test_prefers_cost_details_over_calculated(self) -> None:
        g1 = _gen_obs(
            "t1",
            "g1",
            1,
            costDetails={"total": 0.010},
            calculatedTotalCost=0.005,
        )
        traces = (_turn_trace("t1", 0, 10, g1),)
        result = session_cost(traces)
        assert isinstance(result, float)
        assert abs(result - 0.010) < 1e-9

    def test_no_cost_data_is_a_problem(self) -> None:
        g1 = _gen_obs("t1", "g1", 1)
        traces = (_turn_trace("t1", 0, 10, g1),)
        result = session_cost(traces)
        assert isinstance(result, Problem)
        assert result.kind == "missing"

    def test_empty_traces_is_a_problem(self) -> None:
        result = session_cost(())
        assert isinstance(result, Problem)
        assert result.kind == "missing"

    def test_sums_across_multiple_traces(self) -> None:
        g1 = _gen_obs("t1", "g1", 1, costDetails={"total": 0.003})
        g2 = _gen_obs("t2", "g2", 6, calculatedTotalCost=0.007)
        traces = (_turn_trace("t1", 0, 5, g1), _turn_trace("t2", 5, 10, g2))
        result = session_cost(traces)
        assert isinstance(result, float)
        assert abs(result - 0.010) < 1e-9

    def test_ignores_non_generation_observations(self) -> None:
        tool = Observation.model_validate(
            {
                "id": "tc1",
                "traceId": "t1",
                "startTime": _t(1).isoformat(),
                "type": "TOOL",
                "parentObservationId": "t1-root",
                "costDetails": {"total": 999.0},
            }
        )
        traces = (_turn_trace("t1", 0, 10, tool),)
        result = session_cost(traces)
        assert isinstance(result, Problem)
