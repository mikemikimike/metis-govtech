"""FactualAccuracyGrader: whether factual claims agree with designated ground truth."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import judge, section
from metis.library.scope import SCOPE_DEFINITIONS, ArtifactArgs, TraceArgs
from metis.library.taxonomy import (
    Aggregation,
    GraderTaxonomy,
    GraderType,
    JudgmentForm,
    Measure,
    ReferenceType,
    Scope,
)
from metis.library.text import NonEmptyText  # noqa: TC001 — a Pydantic field type

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import LLMSettings


class FactualAccuracyArgs(JudgeArgs, TraceArgs, ArtifactArgs):
    """Settings for the factual-accuracy assessment.

    ``ground_truth`` is the authoritative reference. Claims not addressed by the
    ground truth are outside the scope of this assessment. The grader does not use
    the judge's own knowledge.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    ground_truth: tuple[NonEmptyText, ...] = Field(
        min_length=1,
        description="Authoritative facts to check claims against.",
    )


class FactualAccuracyGrader(Grader[FactualAccuracyArgs]):
    """Assess whether factual claims agree with the designated authoritative ground truth.

    Compares claims against the supplied ground truth only. Does not substitute the
    judge's own knowledge. Partial reference coverage is noted in the reason. Evidence with
    no claim that the ground truth addresses is errored, with the judge's reason.
    """

    args_model = FactualAccuracyArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.FACTUAL_ACCURACY,
        scopes=(Scope.TRACE, Scope.ARTIFACT),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether factual claims in the assessed evidence agree with "
            "the designated authoritative ground truth."
            + section("ground_truth", self.args.ground_truth)
            + "\n\n<assessment_boundaries>\n"
            "Compare factual claims with the designated ground truth above ONLY. Do not "
            "substitute your own knowledge or unsupported recollection. A claim that the "
            "ground truth does not address is outside the scope of this assessment; note "
            "partial coverage in your reason when some claims could not be checked. A claim "
            "contradicted by the ground truth is inaccurate. A response can be complete and "
            "well-structured but still contain an incorrect fact. If the assessed evidence "
            "contains no factual claims assessable against the ground truth, the criterion "
            "does not apply."
            "\n</assessment_boundaries>"
        )

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        scope = SCOPE_DEFINITIONS[self.scope]
        selected = scope.select(input, self.args)
        if isinstance(selected, Problem):
            return GradingOutput.errored(selected.detail)
        return GradingOutput(
            results=[
                await judge(self, llm, label, scope.render(thing), self.criteria())
                for label, thing in selected.items()
            ]
        )
