"""Output Verification metric (M-DA-27)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import (
    get_artifacts,
    get_completion_claims,
    get_executed_code,
)
from ._judge import _get_judge_model

# Code fragments that indicate an existence/verification check on outputs.
_VERIFY_PATTERNS = (
    "os.path.exists",
    "os.path.isfile",
    "os.listdir",
    ".exists()",
    "glob(",
    "glob.glob",
    "listdir(",
    "isfile(",
    "assert os.path",
)


def _verification_evidence(test_case: LLMTestCase) -> str:
    code = "\n".join(get_executed_code(test_case)).lower()
    verify_hits = sorted({p for p in _VERIFY_PATTERNS if p in code})
    artifacts = [a.get("filename", "") for a in get_artifacts(test_case)]
    lines = [
        "Verification patterns in executed code: "
        + (", ".join(verify_hits) if verify_hits else "none detected"),
        "Collected output artifacts: "
        + (", ".join(a for a in artifacts if a) or "none recorded"),
    ]
    return "\n".join(lines)


class OutputVerificationMetric(MetisTurnMetric):
    """Did the agent verify output files exist before declaring done?

    Judge-graded (M-DA-27). Applicable only when the agent claims the
    deliverables are ready. Assesses whether a verification step (checking the
    files exist in outputs/) precedes that claim, using the executed code and
    collected artifacts as evidence. Skips when no completion claim is made.
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
                name="Output Verification",
                model=_get_judge_model(),
                criteria=(
                    "Before telling the user the deliverables are ready, the "
                    "agent should verify the deliverable files exist in "
                    "outputs/; using the agent's completion claim, the executed "
                    "code, and the collected output artifacts, judge whether a "
                    "verification step (checking files exist / listing outputs) "
                    "precedes the completion claim.\n\n"
                    "The 'input' is the user's request; the 'context' "
                    "summarises verification patterns in the executed code and "
                    "the collected artifacts; the 'actual_output' is the "
                    "agent's completion response.\n\n"
                    "Assess whether the agent verified the deliverables exist "
                    "before declaring them ready — for example by checking the "
                    "files exist in outputs/, listing the directory, or "
                    "confirming the saved paths — rather than claiming "
                    "completion blindly.\n\n"
                    "Score 1.0 when a clear verification step precedes the "
                    "completion claim. "
                    "Score 0.5 when verification is implicit or partial. "
                    "Score 0.0 when the agent declares the deliverables ready "
                    "with no evidence that it checked they exist."
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
            context=[_verification_evidence(test_case)],
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        if not get_completion_claims(test_case):
            return mark_skipped(
                self,
                "no completion claim on this turn; output "
                "verification is not applicable.",
            )
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
        return "Output Verification"

    def is_successful(self) -> bool:
        return self.success is True
