"""M-UNI-10: Assumption Transparency metric."""

from typing import ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, SyncBaseMetric, _ContextAwareGEval
from ._judge import _get_judge_model


class AssumptionTransparencyMetric(SyncBaseMetric):
    """Assumptions explicitly stated to user?

    Full judge: evaluates whether the agent makes its assumptions visible.
    """

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Assumption Transparency",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the agent explicitly "
                    "states assumptions it made.\n\n"
                    "SYSTEM CONTEXT: This agent is an "
                    "orchestrator that delegates tasks "
                    "to "
                    "specialised subagents (Data "
                    "Analyst, Slide Maker, Text "
                    "Analyst, etc.). "
                    "Delegating a task to the correct "
                    "subagent is STANDARD BEHAVIOUR, "
                    "not an "
                    "assumption. Routing decisions, "
                    "tool usage, and reading file "
                    "contents are "
                    "normal operations — do NOT count "
                    "these as 'unstated "
                    "assumptions.'\n\n"
                    "The 'input' is the user's request "
                    "(which may be ambiguous or "
                    "underspecified).\n"
                    "The 'actual_output' is the agent's "
                    "response.\n\n"
                    "Only flag these as unstated "
                    "assumptions:\n"
                    "- Interpreting an ambiguous user "
                    "request one way without saying so\n"
                    "- Choosing a scope/format/timeframe "
                    "the user didn't specify\n"
                    "- Making analytical choices "
                    "(grouping, filtering, method) "
                    "without explaining\n\n"
                    "Do NOT flag as unstated "
                    "assumptions:\n"
                    "- Delegating to a subagent (this is "
                    "the system's normal workflow)\n"
                    "- Reading a file the user "
                    "uploaded\n"
                    "- Using available tools to "
                    "accomplish the task\n"
                    "- Identifying column names from a "
                    "CSV (this is observation, not "
                    "assumption)\n\n"
                    "Score 1.0 if all assumptions are "
                    "transparently stated, or no "
                    "assumptions needed. "
                    "Score 0.5 if some assumptions "
                    "stated but others implicit. "
                    "Score 0.0 if the agent clearly made "
                    "scope/interpretation "
                    "assumptions but never mentioned "
                    "them. "
                    "If the task required no assumptions "
                    "(fully specified), score 1.0." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Assumption Transparency"

    def is_successful(self) -> bool:
        return self.success is True
