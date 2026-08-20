"""
Result types for the three-phase evaluation orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from metis.engine.extractor.types import RoutingSummary


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

    llm_test_case: LLMTestCase
    metric_results: list[MetricResult]


@dataclass
class SessionResult:
    """Result of evaluating session metrics against a ConversationalTestCase."""

    conversational_test_case: ConversationalTestCase
    metric_results: list[MetricResult]


@dataclass
class EvalDurations:
    """Wall-clock time spent in each evaluation phase (seconds)."""

    turn_metrics_seconds: float = 0.0
    session_metrics_seconds: float = 0.0


@dataclass
class EvalResult:
    """Result of an evaluation run.

    :param turn_results: Per-turn metric results (each contains the LLMTestCase and its metrics).
    :param session_results: Per-session metric results (each contains the ConversationalTestCase and its metrics).
    :param routing_summary: Aggregate routing statistics.
    :param durations: Wall-clock time spent in each evaluation phase.
    """

    turn_results: list[TurnResult] = field(default_factory=list)
    session_results: list[SessionResult] = field(default_factory=list)
    routing_summary: RoutingSummary = field(
        default_factory=lambda: RoutingSummary(
            total_traces=0,
            total_sessions=0,
            direct_handle=0,
            routing_failed=0,
            subagent_counts={},
        )
    )
    durations: EvalDurations = field(default_factory=EvalDurations)

    @classmethod
    def merge(cls, results: list[EvalResult]) -> EvalResult:
        """Merge multiple EvalResults into a single aggregate."""
        merged_turn_results: list[TurnResult] = []
        merged_session_results: list[SessionResult] = []
        merged_durations = EvalDurations()
        total_traces = 0
        total_sessions = 0
        direct_handle = 0
        routing_failed = 0
        subagent_counts: dict = {}

        for r in results:
            merged_turn_results.extend(r.turn_results)
            merged_session_results.extend(r.session_results)
            merged_durations.turn_metrics_seconds += r.durations.turn_metrics_seconds
            merged_durations.session_metrics_seconds += r.durations.session_metrics_seconds
            total_traces += r.routing_summary["total_traces"]
            total_sessions += r.routing_summary["total_sessions"]
            direct_handle += r.routing_summary["direct_handle"]
            routing_failed += r.routing_summary["routing_failed"]
            for agent, count in r.routing_summary["subagent_counts"].items():
                subagent_counts[agent] = subagent_counts.get(agent, 0) + count

        return cls(
            turn_results=merged_turn_results,
            session_results=merged_session_results,
            routing_summary=RoutingSummary(
                total_traces=total_traces,
                total_sessions=total_sessions,
                direct_handle=direct_handle,
                routing_failed=routing_failed,
                subagent_counts=subagent_counts,
            ),
            durations=merged_durations,
        )
