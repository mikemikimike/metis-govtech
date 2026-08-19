"""Gap Acknowledgement metric (M-ORCA-*)."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisTurnMetric, _ContextAwareGEval, mark_skipped
from ._judge import _get_judge_model
from ._types import TraceMetadata


class GapAcknowledgementMetric(MetisTurnMetric):
    """Gaps in subagent output explicitly noted?

    Extract+judge: checks whether Orca acknowledges gaps/uncertainties in
    the subagent's response rather than silently passing them through.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "judge-graded",
    )

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Gap Acknowledgement",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator "
                    "acknowledges gaps or uncertainties "
                    "in the subagent's output.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "final response.\n"
                    "The 'context' contains the subagent's raw "
                    "output.\n\n"
                    "Check:\n"
                    "1. Are there gaps in the subagent output "
                    "(missing data, unanswered parts, "
                    "hedged conclusions, caveats)?\n"
                    "2. If yes, does the orchestrator explicitly "
                    "acknowledge them to the user?\n"
                    "3. Does it avoid presenting incomplete "
                    "information as if it were complete?\n\n"
                    "Score 1.0 if no gaps exist or all gaps are "
                    "acknowledged. "
                    "When scoring 1.0, state ONLY: "
                    "'No unacknowledged gaps detected.' "
                    "Do not describe what the response "
                    "covered.\n"
                    "Score 0.5 if some gaps noted but others "
                    "silently ignored — "
                    "quote the ignored gap.\n"
                    "Score 0.0 if obvious gaps passed through "
                    "without mention — "
                    "quote the gap and the point where "
                    "acknowledgement was missing." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.CONTEXT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        subagent_output = delegation.get("response", "") if delegation else ""
        if not subagent_output and test_case.context:
            subagent_output = test_case.context[0]

        if not subagent_output:
            return mark_skipped(self, "No subagent output to check for gaps")

        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[subagent_output],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(judge_tc)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Gap Acknowledgement"

    def is_successful(self) -> bool:
        return self.success is True
