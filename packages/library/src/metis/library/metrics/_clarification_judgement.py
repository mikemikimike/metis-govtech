"""Clarification Judgement metric (M-ORCA-*)."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class ClarificationJudgementMetric(MetisMetric):
    """Asks when ambiguous, skips when clear?

    Extract+judge: given annotation of whether the query is ambiguous or clear,
    checks whether Orca's behaviour matches (clarify for ambiguous, proceed for clear).
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
                name="Clarification Judgement",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator correctly "
                    "judged whether to ask for "
                    "clarification or proceed directly.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is what the orchestrator "
                    "did (asked a question or proceeded).\n\n"
                    "A good orchestrator:\n"
                    "- Asks for clarification when the request "
                    "has multiple valid interpretations\n"
                    "- Proceeds directly when intent is clear "
                    "and unambiguous\n"
                    "- Does NOT ask unnecessary clarifications "
                    "for clear requests\n"
                    "- Does NOT barrel ahead on genuinely "
                    "ambiguous requests\n\n"
                    "Score 1.0 if the clarification decision "
                    "was correct. "
                    "Score 0.5 if borderline (request was "
                    "somewhat ambiguous and agent's choice "
                    "was defensible). "
                    "Score 0.0 if clearly wrong (asked when "
                    "obvious, or proceeded when genuinely "
                    "ambiguous)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Clarification Judgement"

    def is_successful(self) -> bool:
        return self.success is True
