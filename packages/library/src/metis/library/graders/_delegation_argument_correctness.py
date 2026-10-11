"""Delegation Argument Correctness grader (M-ORCA-*)."""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from deepeval.metrics import (
    ArgumentCorrectnessMetric as _ArgumentCorrectnessMetric,
)
from deepeval.test_case import LLMTestCase, ToolCall

from ._base import MetisTurnGrader, _with_eval_context, mark_skipped
from ._judge import _get_judge_model

if TYPE_CHECKING:
    from ._types import LlmTestCaseMetadata


class DelegationArgumentCorrectnessGrader(MetisTurnGrader):
    """Delegation argument correctness — new grader.

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

    def __init__(self) -> None:
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._grader = None

    def _get_grader(self) -> _ArgumentCorrectnessMetric:
        if self._grader is None:
            self._grader = _ArgumentCorrectnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._grader

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata)
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

        grader = self._get_grader()
        grader.measure(arg_tc)
        self.score = grader.score
        self._accrue_cost(grader.evaluation_cost)
        self._accrue_tokens(grader.input_tokens, grader.output_tokens)
        self.reason = grader.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Delegation Argument Correctness"

    def is_successful(self) -> bool:
        return self.success is True
