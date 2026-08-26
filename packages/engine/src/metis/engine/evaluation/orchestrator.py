"""Evaluation orchestrator with custom metric execution loop."""

import asyncio
import copy
import importlib
import time
from collections.abc import Sequence

from deepeval.metrics import BaseMetric
from deepeval.metrics.base_metric import BaseConversationalMetric
from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from metis.engine.evaluation.types import (
    EvalDurations,
    EvalResult,
    MetricResult,
    SessionResult,
    TurnResult,
)
from metis.engine.extractor.langfuse import FetchLangfuseResult
from metis.engine.extractor.types import RoutingSummary
from metis.engine.simulation.types import MetricRef


def _resolve_metrics(metric_refs: list[MetricRef]) -> list[BaseMetric]:
    """Instantiate metric classes from :class:`MetricRef` objects."""
    metrics: list[BaseMetric] = []
    for ref in metric_refs:
        module_path, class_name = ref.fqn.rsplit(".", 1)
        cls = getattr(importlib.import_module(module_path), class_name)
        metrics.append(cls(**ref.args))
    return metrics


async def _run_metric(
    metric: BaseMetric | BaseConversationalMetric,
    test_case: LLMTestCase | ConversationalTestCase,
    semaphore: asyncio.Semaphore,
) -> MetricResult:
    """Evaluate a single metric against a test case."""
    async with semaphore:
        metric_copy = copy.deepcopy(metric)
        try:
            if metric_copy.async_mode:
                await metric_copy.a_measure(test_case)  # type: ignore[arg-type]
            else:
                await asyncio.to_thread(metric_copy.measure, test_case)  # type: ignore[arg-type]
        except Exception as exc:
            metric_copy.score = 0.0
            metric_copy.reason = f"Metric raised: {type(exc).__name__}: {exc}"
            metric_copy.success = False
        return MetricResult(
            name=metric_copy.__name__,
            score=metric_copy.score,
            reason=metric_copy.reason or "",
            success=metric_copy.is_successful() or False,
            skipped=metric_copy.skipped,
            evaluation_cost=getattr(metric_copy, "evaluation_cost", None),
            input_tokens=getattr(metric_copy, "input_tokens", None),
            output_tokens=getattr(metric_copy, "output_tokens", None),
        )


async def _evaluate_turn_metrics(
    test_cases: list[LLMTestCase],
    metrics: list[BaseMetric],
    *,
    concurrency: int = 50,
) -> list[TurnResult]:
    """Run per-turn metrics against LLMTestCase objects."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[TurnResult] = []

    for test_case in test_cases:
        tasks = [_run_metric(m, test_case, semaphore) for m in metrics]
        metric_results = await asyncio.gather(*tasks)
        results.append(
            TurnResult(llm_test_case=test_case, metric_results=list(metric_results))
        )

    return results


async def _evaluate_session_metrics(
    test_cases: list[ConversationalTestCase],
    metrics: Sequence[BaseConversationalMetric],
    *,
    concurrency: int = 50,
) -> list[SessionResult]:
    """Run session metrics against ConversationalTestCase objects."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[SessionResult] = []

    for test_case in test_cases:
        tasks = [_run_metric(m, test_case, semaphore) for m in metrics]
        metric_results = await asyncio.gather(*tasks)
        results.append(
            SessionResult(
                conversational_test_case=test_case, metric_results=list(metric_results)
            )
        )

    return results


def evaluate(
    fetch_result: FetchLangfuseResult,
    metric_refs: list[MetricRef],
    *,
    concurrency: int = 50,
    throttle: int = 5,
) -> EvalResult:
    """Evaluate test cases using metrics specified as FQN class references.

    Metrics are split automatically by type:
    - :class:`deepeval.metrics.base_metric.BaseConversationalMetric` subclasses
      run against :attr:`FetchLangfuseResult.session_test_cases` (one per session).
    - All other metrics run against :attr:`FetchLangfuseResult.test_cases`
      (one per trace/turn).

    This means session metrics and per-turn metrics can be listed together
    in ``experiment.yaml`` — no annotation needed.

    :param fetch_result: Output of :func:`metis.engine.extractor.langfuse.fetch_by_session_id`.
    :param metric_refs: List of :class:`~metis.engine.simulation.types.MetricRef` objects.
    :param concurrency: Max parallel metric judge calls.
    :param throttle: Unused; retained for API compatibility.
    :returns: :class:`EvalResult` with per-turn and session results merged.
    """
    test_cases = fetch_result.test_cases
    session_test_cases = fetch_result.session_test_cases

    if not test_cases:
        return EvalResult()

    all_metrics = _resolve_metrics(metric_refs)
    if not all_metrics:
        return EvalResult()

    per_turn_metrics = [
        m for m in all_metrics if not isinstance(m, BaseConversationalMetric)
    ]
    session_metrics = [
        m for m in all_metrics if isinstance(m, BaseConversationalMetric)
    ]

    durations = EvalDurations()

    # Per-turn evaluation
    per_turn_results: list[TurnResult] = []
    if per_turn_metrics:
        t0 = time.time()
        per_turn_results = asyncio.run(
            _evaluate_turn_metrics(
                test_cases, per_turn_metrics, concurrency=concurrency
            )
        )
        durations.turn_metrics_seconds = round(time.time() - t0, 1)

    # Session evaluation
    session_results: list[SessionResult] = []
    if session_metrics and session_test_cases:
        t0 = time.time()
        session_results = asyncio.run(
            _evaluate_session_metrics(
                session_test_cases, session_metrics, concurrency=concurrency
            )
        )
        durations.session_metrics_seconds = round(time.time() - t0, 1)

    routing_summary = RoutingSummary(
        total_traces=len(test_cases),
        total_sessions=len(fetch_result.sessions),
        direct_handle=len(test_cases),
        routing_failed=0,
        subagent_counts={},
    )

    return EvalResult(
        turn_results=per_turn_results,
        session_results=session_results,
        routing_summary=routing_summary,
        durations=durations,
    )
