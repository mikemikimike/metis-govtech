"""Evaluation orchestrator with custom grader execution loop."""

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
    GraderResult,
    SessionResult,
    TurnResult,
)
from metis.engine.extractor.langfuse import FetchLangfuseResult
from metis.engine.extractor.types import RoutingSummary
from metis.engine.simulation.types import GraderRef


def _resolve_graders(grader_refs: list[GraderRef]) -> list[BaseMetric]:
    """Instantiate grader classes from :class:`GraderRef` objects."""
    graders: list[BaseMetric] = []
    for ref in grader_refs:
        module_path, class_name = ref.fqn.rsplit(".", 1)
        cls = getattr(importlib.import_module(module_path), class_name)
        grader = cls(**ref.args)
        grader._metis_ref = ref
        graders.append(grader)
    return graders


async def _run_grader(
    grader: BaseMetric | BaseConversationalMetric,
    test_case: LLMTestCase | ConversationalTestCase,
    semaphore: asyncio.Semaphore,
) -> GraderResult:
    """Evaluate a single grader against a test case."""
    async with semaphore:
        grader_copy = copy.deepcopy(grader)
        try:
            if grader_copy.async_mode:
                await grader_copy.a_measure(test_case)  # type: ignore[arg-type]
            else:
                await asyncio.to_thread(grader_copy.measure, test_case)  # type: ignore[arg-type]
        except Exception as exc:
            grader_copy.score = 0.0
            grader_copy.reason = f"Grader raised: {type(exc).__name__}: {exc}"
            grader_copy.success = False
        ref = getattr(grader, "_metis_ref", None)
        return GraderResult(
            criterion_id=ref.criterion_id if ref else "",
            grader_fqn=ref.fqn if ref else "",
            grader_args=dict(ref.args) if ref else {},
            name=grader_copy.__name__,
            score=grader_copy.score,
            reason=grader_copy.reason or "",
            success=grader_copy.is_successful() or False,
            skipped=grader_copy.skipped,
            evaluation_cost=getattr(grader_copy, "evaluation_cost", None),
            input_tokens=getattr(grader_copy, "input_tokens", None),
            output_tokens=getattr(grader_copy, "output_tokens", None),
        )


async def _evaluate_turn_graders(
    test_cases: list[LLMTestCase],
    graders: list[BaseMetric],
    *,
    concurrency: int = 50,
) -> list[TurnResult]:
    """Run per-turn graders against LLMTestCase objects."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[TurnResult] = []

    for test_case in test_cases:
        tasks = [_run_grader(g, test_case, semaphore) for g in graders]
        grader_results = await asyncio.gather(*tasks)
        results.append(
            TurnResult(llm_test_case=test_case, grader_results=list(grader_results))
        )

    return results


async def _evaluate_session_graders(
    test_cases: list[ConversationalTestCase],
    graders: Sequence[BaseConversationalMetric],
    *,
    concurrency: int = 50,
) -> list[SessionResult]:
    """Run session graders against ConversationalTestCase objects."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[SessionResult] = []

    for test_case in test_cases:
        tasks = [_run_grader(g, test_case, semaphore) for g in graders]
        grader_results = await asyncio.gather(*tasks)
        results.append(
            SessionResult(
                conversational_test_case=test_case, grader_results=list(grader_results)
            )
        )

    return results


def evaluate(
    fetch_result: FetchLangfuseResult,
    grader_refs: list[GraderRef],
    *,
    concurrency: int = 50,
    throttle: int = 5,
    task_id: str = "",
    trial_index: int = 1,
) -> EvalResult:
    """Evaluate test cases using graders specified as FQN class references.

    Graders are split automatically by type:
    - :class:`deepeval.metrics.base_metric.BaseConversationalMetric` subclasses
      run against :attr:`FetchLangfuseResult.session_test_cases` (one per session).
    - All other graders run against :attr:`FetchLangfuseResult.test_cases`
      (one per trace/turn).

    This means session graders and per-turn graders can be listed together
    in ``specification.yaml`` — no annotation needed.

    :param fetch_result: Output of :func:`metis.engine.extractor.langfuse.fetch_by_session_id`.
    :param grader_refs: List of :class:`~metis.engine.simulation.types.GraderRef` objects.
    :param concurrency: Max parallel grader judge calls.
    :param throttle: Unused; retained for API compatibility.
    :returns: :class:`EvalResult` with per-turn and session results merged.
    """
    test_cases = fetch_result.test_cases
    session_test_cases = fetch_result.session_test_cases

    if not test_cases:
        return EvalResult()

    all_graders = _resolve_graders(grader_refs)
    if not all_graders:
        return EvalResult()

    per_turn_graders = [
        g for g in all_graders if not isinstance(g, BaseConversationalMetric)
    ]
    session_graders = [
        g for g in all_graders if isinstance(g, BaseConversationalMetric)
    ]

    durations = EvalDurations()

    # Per-turn evaluation
    per_turn_results: list[TurnResult] = []
    if per_turn_graders:
        t0 = time.time()
        per_turn_results = asyncio.run(
            _evaluate_turn_graders(
                test_cases, per_turn_graders, concurrency=concurrency
            )
        )
        durations.turn_graders_seconds = round(time.time() - t0, 1)

    # Session evaluation
    session_results: list[SessionResult] = []
    if session_graders and session_test_cases:
        t0 = time.time()
        session_results = asyncio.run(
            _evaluate_session_graders(
                session_test_cases, session_graders, concurrency=concurrency
            )
        )
        durations.session_graders_seconds = round(time.time() - t0, 1)

    for result in [*per_turn_results, *session_results]:
        for score in result.grader_results:
            score.task_id = task_id
            score.trial_index = trial_index

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
