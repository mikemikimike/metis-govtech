"""Synthesis Faithfulness metric (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric, _with_eval_context
from ._judge import _get_judge_model
from ._types import TraceMetadata


class SynthesisFaithfulnessMetric(SyncBaseMetric):
    """Synthesis faithfulness — AC-ORCA-6.

    Does the orchestrator's response faithfully represent what the subagent
    returned? Extracts subagent output from delegation.response and passes it
    as retrieval_context to DeepEval's built-in FaithfulnessMetric.
    Skips if no subagent output is available.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "judge-graded",
    )

    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = FaithfulnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        subagent_output = delegation.get("response", "") if delegation else ""
        if not subagent_output and test_case.context:
            subagent_output = test_case.context[0]

        if not subagent_output:
            self.score = 1.0
            self.skipped = True
            self.reason = (
                "No subagent output available for faithfulness check — SKIPPED"
            )
            self.success = True
            return self.score or 0.0

        if not test_case.actual_output or not test_case.actual_output.strip():
            self.score = 1.0
            self.skipped = True
            self.reason = "Empty actual_output — no Orca response to evaluate — SKIPPED"
            self.success = True
            return self.score or 0.0

        synthesis_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                retrieval_context=[subagent_output],
                metadata=test_case.metadata,
            )
        )

        metric = self._get_metric()
        metric.measure(synthesis_tc)
        self.score = metric.score
        self.evaluation_cost = getattr(metric, "evaluation_cost", None)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Synthesis Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
