"""Report Format and Length grader (M-DA-12)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import EVIDENCE_INSTRUCTION, MetisTurnGrader, _ContextAwareGEval
from ._extraction import get_artifacts
from ._judge import _get_judge_model


def _artifact_facts(test_case: LLMTestCase) -> str:
    files = [a.name for a in get_artifacts(test_case)]
    return ", ".join(str(f) for f in files) if files else "(no artifact files recorded)"


class ReportFormatAndLengthGrader(MetisTurnGrader):
    """Is the report format correct and its length proportionate? (M-DA-12)

    Judge-graded across two dimensions: (1) correct, consistent format — never
    substituting a .txt file for a requested format; (2) length proportionate
    to the query scope. The narrow ChartFormatCompliance /
    ReportLengthAppropriateness helpers remain available.
    """

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Report Format and Length",
                model=_get_judge_model(),
                criteria=(
                    "The report should be in the correct format with "
                    "consistent formatting, and its length should be "
                    "proportionate to the query scope; a .txt file should never "
                    "be substituted for a requested format. Using the delivered "
                    "report file(s) and the agent's response, judge format "
                    "correctness/consistency and length-vs-scope "
                    "proportionality.\n\n"
                    "The 'input' is the user's request; the 'context' lists "
                    "the delivered artifact files; the 'actual_output' is the "
                    "agent's response.\n\n"
                    "Assess two dimensions:\n"
                    "1. Format: Is the output in the requested/appropriate "
                    "format with consistent formatting? A plain .txt file "
                    "delivered where a specific format (e.g. .md, .pdf, .xlsx, "
                    ".csv) was requested fails this dimension.\n"
                    "2. Length: Is the length proportionate to the scope of "
                    "the query — neither a one-liner for a broad ask nor a "
                    "sprawling report for a narrow one?\n\n"
                    "Score 1.0 when both format and length are appropriate. "
                    "Score 0.5 when one dimension is weak. "
                    "Score 0.0 when the format is wrong (including a wrong .txt "
                    "substitution) or the length is badly disproportionate."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase) -> LLMTestCase:
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=["Delivered files: " + _artifact_facts(test_case)],
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Report Format and Length"

    def is_successful(self) -> bool:
        return self.success is True
