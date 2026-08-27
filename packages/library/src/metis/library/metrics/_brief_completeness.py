"""Brief Completeness metric (M-SM-8)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import extract_brief, extract_source_texts
from ._judge import _get_judge_model


class BriefCompletenessMetric(MetisTurnMetric):
    """All key source information represented in the brief? (M-SM-8)

    Extract-and-judge. Compares the extracted brief against the source
    documents and scores whether the key source information is represented.
    Skips when either the brief or the source material is unavailable.
    """

    tags: ClassVar[tuple[str, ...]] = ("presentation", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Brief Completeness",
                model=_get_judge_model(),
                criteria=(
                    "The brief represents all the key information from the "
                    "source material; compare the extracted brief against the "
                    "source documents and judge whether the key source "
                    "information is represented, without material omissions."
                    "\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the source documents; the 'actual_output' is the "
                    "extracted brief.\n\n"
                    "Assess whether the brief represents all the key "
                    "information present in the sources — the main facts, "
                    "figures, and themes needed for the deck — without leaving "
                    "out material points.\n\n"
                    "Score 1.0 when all key source information is represented. "
                    "Score 0.5 when the brief covers the main points but omits "
                    "some notable ones. "
                    "Score 0.0 when key source information is missing."
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

    def _augmented(
        self, test_case: LLMTestCase, brief: str, sources: list
    ) -> LLMTestCase:
        return LLMTestCase(
            input=test_case.input,
            actual_output=brief,
            context=["Source documents:\n" + "\n\n---\n\n".join(sources)],
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        brief = extract_brief(test_case)
        sources = extract_source_texts(test_case)
        if not brief or not sources:
            return mark_skipped(
                self,
                "brief or source material unavailable; brief "
                "completeness cannot be assessed.",
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, brief, sources))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Brief Completeness"

    def is_successful(self) -> bool:
        return self.success is True
