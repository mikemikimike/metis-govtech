"""Checklist validation and grader-specific judge helpers.

Generic LLM call and transcript rendering live in ``metis.library.judge_call``.
This module keeps the ``metis.library.graders._judge_call`` import path working
for all symbols and adds the checklist-specific models and validation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from metis.core.grading import GraderResult
from metis.library.grader import NonEmptyText

# Re-export generic helpers so existing ``from ._judge_call import …`` still works.
from metis.library.judge_call import (
    get_session_turns as get_session_turns,
)
from metis.library.judge_call import (
    judge_call as judge_call,
)
from metis.library.judge_call import (
    render_transcript_with_tool_results as render_transcript_with_tool_results,
)

# ---------------------------------------------------------------------------
# Response models for per-item (checklist) graders
# ---------------------------------------------------------------------------


class ChecklistAssessment(BaseModel):
    """One item's assessment within a checklist grader.

    ``id`` must match the stable ID assigned to a configured item.
    ``verdict`` distinguishes met, not met, and insufficient evidence.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="The stable ID of the assessed item.")
    verdict: Literal["met", "not_met", "insufficient_evidence"] = Field(
        description="Whether the item was satisfied, not satisfied, or could not be assessed."
    )
    reason: NonEmptyText


class ChecklistResponse(BaseModel):
    """The judge's per-item assessment list for checklist graders."""

    model_config = ConfigDict(extra="forbid")

    assessments: list[ChecklistAssessment]


# Legacy response models kept for backward compatibility if needed
class ItemAssessment(BaseModel):
    """One item's binary assessment within a per-item grader."""

    model_config = ConfigDict(extra="forbid")

    item: NonEmptyText
    met: bool
    reason: NonEmptyText


class ItemAssessmentList(BaseModel):
    """Per-item assessments returned by completeness and constraint graders."""

    model_config = ConfigDict(extra="forbid")

    assessments: list[ItemAssessment]


# ---------------------------------------------------------------------------
# Checklist validation
# ---------------------------------------------------------------------------


def validate_checklist(
    response: ChecklistResponse,
    expected_ids: tuple[str, ...],
) -> list[GraderResult] | GraderResult:
    """Validate that the judge returned exactly one assessment per expected ID.

    Returns a list of individual ``GraderResult``s (one per item) if the response
    can be interpreted, or a single errored ``GraderResult`` if the judge response
    itself is malformed (duplicate IDs or extra IDs — signs the judge confused items).

    When the judge omits some expected items but the remaining assessments are valid,
    the valid items are scored and the omitted items are reported as errored.  An
    ``insufficient_evidence`` verdict for one item produces an errored result for
    that item without suppressing scores for other items.
    """
    returned_ids = [a.id for a in response.assessments]
    expected_set = set(expected_ids)
    returned_set = set(returned_ids)

    if len(returned_ids) != len(returned_set):
        duplicates = [id_ for id_ in returned_ids if returned_ids.count(id_) > 1]
        return GraderResult(
            status="errored",
            reason=f"The judge returned duplicate item IDs: {sorted(set(duplicates))}.",
        )

    extra = returned_set - expected_set
    if extra:
        return GraderResult(
            status="errored",
            reason=f"The judge returned unknown item IDs: {sorted(extra)}.",
        )

    by_id = {a.id: a for a in response.assessments}
    missing = expected_set - returned_set

    results: list[GraderResult] = []
    for id_ in expected_ids:
        if id_ in missing:
            results.append(
                GraderResult(
                    status="errored",
                    reason=f"{id_}: the judge omitted this item",
                    scope=f"item:{id_}",
                )
            )
            continue
        a = by_id[id_]
        if a.verdict == "insufficient_evidence":
            results.append(
                GraderResult(
                    status="errored",
                    reason=f"{a.id}: insufficient evidence — {a.reason}",
                    scope=f"item:{a.id}",
                )
            )
        else:
            results.append(
                GraderResult(
                    status="scored",
                    score=1.0 if a.verdict == "met" else 0.0,
                    reason=f"{a.id}: {a.reason}",
                    scope=f"item:{a.id}",
                )
            )
    return results


def score_checklist(item_results: list[GraderResult]) -> GraderResult | None:
    """Compute the aggregate score from validated checklist item results.

    Score = met_count / scored_count, covering only items the judge could assess.
    Errored items (e.g. insufficient evidence) are excluded from the denominator
    but reported in the coverage.  Returns ``None`` when no item was scored.
    """
    scored = [r for r in item_results if r.status == "scored"]
    if not scored:
        return None
    n_scored = len(scored)
    n_total = len(item_results)
    met_count = sum(1 for r in scored if r.score == 1.0)
    score = met_count / n_scored

    parts = [f"{met_count}/{n_scored} items satisfied"]
    n_errored = n_total - n_scored
    if n_errored:
        parts.append(f"{n_errored}/{n_total} could not be assessed")

    not_met = [r.reason for r in scored if r.score == 0.0]
    if not_met:
        parts.append(f"not met: {'; '.join(not_met)}")

    return GraderResult(
        status="scored",
        score=round(score, 4),
        reason=". ".join(parts) + ".",
        scope="aggregate",
    )


def checklist_item_ids(items: tuple[str, ...]) -> tuple[str, ...]:
    """Assign stable IDs to configured checklist items.

    Uses 1-indexed IDs like ``"item_1"``, ``"item_2"``, etc. The actual item text
    is NOT used as the ID, so the judge cannot affect scoring by paraphrasing.
    """
    return tuple(f"item_{i}" for i in range(1, len(items) + 1))


def checklist_prompt_items(items: tuple[str, ...], ids: tuple[str, ...]) -> str:
    """Format checklist items with their stable IDs for the judge prompt."""
    return "\n".join(f"{id_}. {text}" for id_, text in zip(ids, items, strict=True))
