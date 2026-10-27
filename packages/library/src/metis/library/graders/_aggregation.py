"""Equal-weight aggregation over per-scope grader results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from metis.core.grading import GraderResult, GradingOutput

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence

    from metis.library.graders._evidence import ScopedEvidence, SelectedEvidence


class GradeOneCallable(Protocol):
    """Signature for a callback that grades one evidence unit."""

    def __call__(
        self, evidence: SelectedEvidence, scope: str
    ) -> Awaitable[GraderResult]: ...


def aggregate_scored(results: list[GraderResult]) -> GraderResult | None:
    """Equal-weight mean over scored results, or ``None`` when nothing was scored.

    Errored and skipped results are excluded from the denominator. The aggregate
    reason reports coverage: how many scopes were scored out of total applicable.
    """
    scored = [r for r in results if r.status == "scored"]
    if not scored:
        return None
    total = len(results)
    n_scored = len(scored)
    mean = sum(r.score for r in scored if r.score is not None) / n_scored

    parts = [f"{n_scored}/{total} scopes scored"]
    n_errored = sum(1 for r in results if r.status == "errored")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    if n_errored:
        parts.append(f"{n_errored} errored")
    if n_skipped:
        parts.append(f"{n_skipped} skipped")

    return GraderResult(
        status="scored",
        score=round(mean, 4),
        reason=f"Aggregate: {', '.join(parts)}. Mean score {mean:.2f}.",
        scope="aggregate",
    )


def grading_output_with_aggregate(per_scope: list[GraderResult]) -> GradingOutput:
    """All per-scope results, plus an aggregate when at least one is scored.

    If every scope is ungradable (all errored or skipped), the output carries only
    the per-scope results with no aggregate — no score is invented.
    """
    agg = aggregate_scored(per_scope)
    results = list(per_scope)
    if agg is not None:
        results.append(agg)
    return GradingOutput(results=results)


async def results_from_multi_evidence(
    scoped_evidence: Sequence[ScopedEvidence],
    grade_one: GradeOneCallable,
) -> list[GraderResult]:
    """Grade each resolved evidence unit and collect per-scope results.

    For each ``ScopedEvidence``:
    - If evidence is an ``EvidenceError``, produce an errored result with the scope.
    - Otherwise, call ``grade_one(evidence, scope)`` to get a ``GraderResult``.

    A judge failure on one scope is caught locally and does not suppress
    results already obtained or prevent later scopes from being assessed.

    Returns the per-scope results (without an aggregate — the caller decides whether
    to add one via ``grading_output_with_aggregate``).
    """
    from metis.library.graders._evidence import EvidenceError

    per_scope: list[GraderResult] = []
    for item in scoped_evidence:
        if isinstance(item.evidence, EvidenceError):
            per_scope.append(item.evidence.to_result(scope=item.scope))
        else:
            try:
                result = await grade_one(item.evidence, item.scope)
            except Exception as exc:
                result = GraderResult(
                    status="errored",
                    reason=f"Judge failed on {item.scope}: {type(exc).__name__}: {exc}",
                    scope=item.scope,
                )
            per_scope.append(result)
    return per_scope
