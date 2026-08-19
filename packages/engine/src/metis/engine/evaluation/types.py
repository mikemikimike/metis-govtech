"""
Result types for the three-phase evaluation orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from metis.engine.extractor.types import (
    RoutingSummary,
    SessionMetricsEntry,
)


@dataclass
class MetricResult:
    """Result of a single metric evaluation."""

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool
    evaluation_cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class TurnResult:
    """Result of evaluating per-turn metrics against a single LLMTestCase."""

    test_case: LLMTestCase
    metrics: list[MetricResult]


@dataclass
class SessionResult:
    """Result of evaluating session metrics against a ConversationalTestCase."""

    test_case: ConversationalTestCase
    metrics: list[MetricResult]


@dataclass
class EvalResult:
    """Result of an evaluation run.

    :param test_results: Per-trace metric results (each contains the test case and its metrics).
    :param test_cases: The LLMTestCase objects that were evaluated.
    :param routing_summary: Aggregate routing statistics.
    :param trace_routing: Mapping of trace_id → agent_key or ``"direct"``.
    :param session_metrics: Per-session metric results.
    :param timings: Phase durations in seconds.
    """

    test_results: list[TurnResult] = field(default_factory=list)
    test_cases: list[LLMTestCase] = field(default_factory=list)
    routing_summary: RoutingSummary = field(
        default_factory=lambda: RoutingSummary(
            total_traces=0,
            total_sessions=0,
            direct_handle=0,
            routing_failed=0,
            subagent_counts={},
        )
    )
    trace_routing: dict[str, str] = field(default_factory=dict)
    session_metrics: list[SessionMetricsEntry] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    @classmethod
    def merge(cls, results: list[EvalResult]) -> EvalResult:
        """Merge multiple EvalResults into a single aggregate."""
        merged_test_results = []
        merged_test_cases: list[LLMTestCase] = []
        merged_trace_routing: dict[str, str] = {}
        merged_session_metrics: list[SessionMetricsEntry] = []
        merged_timings: dict[str, float] = {}
        total_traces = 0
        total_sessions = 0
        direct_handle = 0
        routing_failed = 0
        subagent_counts: dict = {}

        for r in results:
            merged_test_results.extend(r.test_results)
            merged_test_cases.extend(r.test_cases)
            merged_trace_routing.update(r.trace_routing)
            merged_session_metrics.extend(r.session_metrics)
            for k, v in r.timings.items():
                merged_timings[k] = merged_timings.get(k, 0) + v
            total_traces += r.routing_summary["total_traces"]
            total_sessions += r.routing_summary["total_sessions"]
            direct_handle += r.routing_summary["direct_handle"]
            routing_failed += r.routing_summary["routing_failed"]
            for agent, count in r.routing_summary["subagent_counts"].items():
                subagent_counts[agent] = subagent_counts.get(agent, 0) + count

        return cls(
            test_results=merged_test_results,
            test_cases=merged_test_cases,
            routing_summary=RoutingSummary(
                total_traces=total_traces,
                total_sessions=total_sessions,
                direct_handle=direct_handle,
                routing_failed=routing_failed,
                subagent_counts=subagent_counts,
            ),
            trace_routing=merged_trace_routing,
            session_metrics=merged_session_metrics,
            timings=merged_timings,
        )
