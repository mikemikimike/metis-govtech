"""Synthesis Faithfulness grader (M-ORCA-*)."""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from ._base import MetisTurnGrader, _with_eval_context, mark_skipped
from ._judge import _get_judge_model

if TYPE_CHECKING:
    from ._types import LlmTestCaseMetadata


class SynthesisFaithfulnessGrader(MetisTurnGrader):
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

    def __init__(self) -> None:
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._grader = None

    def _get_grader(self) -> FaithfulnessMetric:
        if self._grader is None:
            self._grader = FaithfulnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._grader

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast("LlmTestCaseMetadata", test_case.metadata)
        delegation = metadata.get("delegation")

        subagent_output = delegation.get("response", "") if delegation else ""
        if not subagent_output and test_case.context:
            subagent_output = test_case.context[0]

        if not subagent_output:
            return mark_skipped(
                self, "No subagent output available for faithfulness check"
            )

        if not test_case.actual_output or not test_case.actual_output.strip():
            return mark_skipped(
                self, "Empty actual_output — no Orca response to evaluate"
            )

        synthesis_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                retrieval_context=[subagent_output],
                metadata=test_case.metadata,
            )
        )

        grader = self._get_grader()
        grader.measure(synthesis_tc)
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
        return "Synthesis Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
