"""Delegation Argument Correctness metric (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.metrics import (
    ArgumentCorrectnessMetric as _ArgumentCorrectnessMetric,
)
from deepeval.test_case import LLMTestCase, ToolCall

from ._base import MetisTurnMetric, _with_eval_context, mark_skipped
from ._judge import _get_judge_model
from ._types import TraceMetadata


class DelegationArgumentCorrectnessMetric(MetisTurnMetric):
    """Delegation argument correctness — new metric.

    Uses DeepEval's built-in ArgumentCorrectnessMetric (referenceless LLM judge)
    to check whether the arguments Orca passed to delegate_task_to_member correctly
    reflect the user's intent. Skips if no delegation occurred.

    Constructs a synthetic ToolCall from delegation metadata so ArgumentCorrectness
    can evaluate the call without requiring @observe tracing.
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
            self._metric = _ArgumentCorrectnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        if not delegation or not delegation["task"]:
            return mark_skipped(self, "No delegation occurred")

        tool_call = ToolCall(
            name="delegate_task_to_member",
            input_parameters={
                "target": delegation["target"],
                "task": delegation["task"],
            },
        )

        arg_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                tools_called=[tool_call],
                metadata=test_case.metadata,
            )
        )

        metric = self._get_metric()
        metric.measure(arg_tc)
        self.score = metric.score
        self._accrue_cost(metric.evaluation_cost)
        self._accrue_tokens(metric.input_tokens, metric.output_tokens)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Delegation Argument Correctness"

    def is_successful(self) -> bool:
        return self.success is True
