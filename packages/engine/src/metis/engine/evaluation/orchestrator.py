"""DeepEval evaluation orchestrator."""

import importlib
import time

from deepeval import evaluate as deepeval_evaluate
from deepeval.evaluate import AsyncConfig, DisplayConfig
from deepeval.metrics import BaseMetric

from metis.engine.evaluation.types import EvalResult
from metis.engine.extractor.langfuse import FetchLangfuseResult
from metis.engine.extractor.types import (
    RoutingSummary,
    SessionMetricResult,
    SessionMetricsEntry,
    SessionToolCallData,
    SessionTurnData,
)
from metis.engine.simulation.types import MetricRef

MAX_CONCURRENCY = 5


def _resolve_metrics(metric_refs: list[MetricRef]) -> list[BaseMetric]:
    """Instantiate metric classes from :class:`MetricRef` objects."""
    metrics: list[BaseMetric] = []
    for ref in metric_refs:
        module_path, class_name = ref.fqn.rsplit(".", 1)
        cls = getattr(importlib.import_module(module_path), class_name)
        metrics.append(cls(**ref.args))
    return metrics


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
    :param concurrency: Max parallel DeepEval judge calls.
    :param throttle: Seconds between DeepEval judge call batches.
    :returns: :class:`EvalResult` with per-turn and session results merged.
    """
    from deepeval.metrics.base_metric import BaseConversationalMetric

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

    async_config = AsyncConfig(
        max_concurrent=min(concurrency, MAX_CONCURRENCY), throttle_value=throttle
    )
    phase_timings: dict[str, float] = {}

    # Per-turn evaluation
    per_turn_results = None
    if per_turn_metrics:
        t0 = time.time()
        per_turn_results = deepeval_evaluate(
            test_cases=test_cases,
            metrics=per_turn_metrics,
            async_config=async_config,
            display_config=DisplayConfig(
                print_results=False, show_indicator=False, inspect_after_run=False
            ),
        )
        phase_timings["per_turn"] = round(time.time() - t0, 1)

    # Session evaluation (serialize to avoid asyncio re-entrancy on Python 3.14)
    session_eval_results = None
    if session_metrics and session_test_cases:
        t0 = time.time()
        session_async_config = AsyncConfig(max_concurrent=1, throttle_value=throttle)
        session_eval_results = deepeval_evaluate(
            test_cases=session_test_cases,
            metrics=session_metrics,
            async_config=session_async_config,
            display_config=DisplayConfig(
                print_results=False, show_indicator=False, inspect_after_run=False
            ),
        )
        phase_timings["session"] = round(time.time() - t0, 1)

    # Build structured session_metrics list for the report
    session_metrics_data: list[SessionMetricsEntry] = []
    if session_eval_results:
        for ctc, sr in zip(
            session_test_cases, session_eval_results.test_results, strict=False
        ):
            sid = (ctc.metadata or {}).get("session_id", "unknown")
            metrics_out: list[SessionMetricResult] = []
            for md in sr.metrics_data or []:
                skipped = md.reason.endswith("— SKIPPED") if md.reason else False
                metrics_out.append(
                    SessionMetricResult(
                        name=md.name,
                        score=md.score,
                        reason=md.reason or "",
                        success=md.success,
                        skipped=skipped,
                    )
                )
            turns_data: list[SessionTurnData] = []
            for t in ctc.turns:
                turn_entry = SessionTurnData(role=t.role, content=t.content[:2000])
                if t.tools_called:
                    turn_entry["tools"] = [
                        SessionToolCallData(
                            name=tc_tool.name,
                            input=str(tc_tool.input_parameters or "")[:300],
                            output=str(tc_tool.output or "")[:300],
                        )
                        for tc_tool in t.tools_called
                    ]
                turns_data.append(turn_entry)

            session_metrics_data.append(
                SessionMetricsEntry(
                    session_id=sid,
                    num_turns=len(ctc.turns) // 2,
                    turns=turns_data,
                    metrics=metrics_out,
                )
            )

    routing_summary = RoutingSummary(
        total_traces=len(test_cases),
        total_sessions=len(fetch_result.sessions),
        direct_handle=len(test_cases),
        routing_failed=0,
        subagent_counts={},
    )

    return EvalResult(
        test_results=per_turn_results.test_results if per_turn_results else [],
        session_results=session_eval_results,
        test_cases=test_cases,
        routing_summary=routing_summary,
        trace_routing={},
        session_metrics=session_metrics_data,
        timings=phase_timings,
    )
