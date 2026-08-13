"""Single source of truth for metric aggregation across report outputs."""

from __future__ import annotations

from typing import Any, TypedDict

from metis.engine.extractor.types import SessionMetricsEntry


class MetricAggregate(TypedDict):
    pass_count: int
    fail: int
    skip: int
    scores: list[float]
    pass_rate: float
    avg_score: float


def aggregate_metrics(
    test_results: list[dict[str, Any]],
    session_metrics: list[SessionMetricsEntry] | None = None,
) -> dict[str, MetricAggregate]:
    """Aggregate pass/fail/skip counts and scores by metric name.

    Processes both per-trace metrics (from test_results) and session-level
    metrics (from session_metrics) into a single unified summary.
    """
    agg: dict[str, MetricAggregate] = {}

    for result in test_results:
        for metric in result.get("metrics", []):
            _accumulate(agg, metric)

    if session_metrics:
        for sess in session_metrics:
            for metric in sess.get("metrics", []):
                _accumulate(agg, metric)

    for entry in agg.values():
        evaluated = entry["pass_count"] + entry["fail"]
        entry["pass_rate"] = entry["pass_count"] / evaluated if evaluated > 0 else 0.0
        entry["avg_score"] = (
            sum(entry["scores"]) / len(entry["scores"]) if entry["scores"] else 0.0
        )

    return agg


def _accumulate(agg: dict[str, MetricAggregate], metric: dict) -> None:
    name = metric["name"]
    if name not in agg:
        agg[name] = MetricAggregate(
            pass_count=0,
            fail=0,
            skip=0,
            scores=[],
            pass_rate=0.0,
            avg_score=0.0,
        )
    entry = agg[name]
    if metric.get("skipped"):
        entry["skip"] += 1
    elif metric["success"]:
        entry["pass_count"] += 1
    else:
        entry["fail"] += 1
    entry["scores"].append(metric["score"])
