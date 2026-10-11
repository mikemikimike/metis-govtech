"""Single source of truth for grader aggregation across report outputs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metis.engine.reporting._types import SessionReport, TurnReport


class GraderAggregate(TypedDict):
    pass_count: int
    fail: int
    skip: int
    scores: list[float]
    pass_rate: float
    avg_score: float


def aggregate_graders(
    turn_results: list[TurnReport],
    session_results: list[SessionReport] | None = None,
) -> dict[str, GraderAggregate]:
    """Aggregate pass/fail/skip counts and scores by Criterion identity.

    Processes both per-trace graders (from turn_results) and session-level
    graders (from session_results) into a single unified summary.
    """
    agg: dict[str, GraderAggregate] = {}

    for result in turn_results:
        for grader in result.get("graders", []):
            _accumulate(agg, grader)

    if session_results:
        for sess in session_results:
            for grader in sess.get("graders", []):
                _accumulate(agg, grader)

    for entry in agg.values():
        evaluated = entry["pass_count"] + entry["fail"]
        entry["pass_rate"] = entry["pass_count"] / evaluated if evaluated > 0 else 0.0
        entry["avg_score"] = (
            sum(entry["scores"]) / len(entry["scores"]) if entry["scores"] else 0.0
        )

    return agg


def _accumulate(agg: dict[str, GraderAggregate], grader: Mapping[str, Any]) -> None:
    name = grader.get("criterion_id") or grader["name"]
    if name not in agg:
        agg[name] = GraderAggregate(
            pass_count=0,
            fail=0,
            skip=0,
            scores=[],
            pass_rate=0.0,
            avg_score=0.0,
        )
    entry = agg[name]
    if grader.get("skipped"):
        entry["skip"] += 1
    elif grader["success"]:
        entry["pass_count"] += 1
    else:
        entry["fail"] += 1
    entry["scores"].append(grader["score"])
