"""Prepare runtime instructions from the stored criterion description."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metis.core.profile import CriterionDescription

CRITERION_JUDGE_FQN = "metis.library.graders.CriterionJudgeGrader"


def prepare_criterion_judge_args(
    description: CriterionDescription, settings: Mapping[str, Any]
) -> dict[str, Any]:
    """Copy settings and derive instructions without changing the stored document."""
    if "criterion" in settings:
        raise ValueError(
            "Edit the criterion description instead of grader_args.criterion."
        )
    for clause in ("given", "when", "then"):
        if not getattr(description, clause).strip():
            raise ValueError(f"Criterion description.{clause} must not be blank.")
    return {**settings, "criterion": str(description)}
