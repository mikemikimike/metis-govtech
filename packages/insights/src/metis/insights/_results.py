"""Validate evaluation files and project recorded results for the report."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from metis.core.reporting import EvaluationResults as RecordedEvaluationResults
from metis.insights._legacy_results import (
    EvaluationResults,
    SessionGraderResult,
    SessionReport,
)

if TYPE_CHECKING:
    from pathlib import Path


def load_results(path: Path) -> EvaluationResults:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "records" not in data:
        return EvaluationResults.model_validate(data)
    recorded = RecordedEvaluationResults.model_validate(data)
    return EvaluationResults(
        run_id=recorded.run_id,
        timings=recorded.timings,
        latency_seconds=recorded.latency_seconds,
        session_results=[
            SessionReport(
                session_id=record.session_id,
                scenario_id=record.scenario_id,
                graders=[
                    SessionGraderResult(
                        criterion_id=record.criterion_id,
                        grader_fqn=record.grader_fqn,
                        grader_args=record.grader_args,
                        task_id=record.task_id,
                        trial_index=record.trial_index,
                        name=record.grader_fqn.rsplit(".", 1)[-1],
                        score=result.score,
                        reason=result.reason,
                        success=result.outcome == "passed",
                        skipped=result.outcome == "skipped",
                        errored=result.outcome == "errored",
                    )
                    for result in record.results
                ],
            )
            for record in recorded.records
        ],
    )
