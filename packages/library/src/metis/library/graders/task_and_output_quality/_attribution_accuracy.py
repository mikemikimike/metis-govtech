"""AttributionAccuracyGrader: whether citations correctly identify supporting evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field, field_validator

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


class AttributionAccuracyArgs(JudgeArgs, TraceArgs, ArtifactArgs):
    """Settings for the attribution-accuracy assessment.

    ``source_materials`` is the authoritative reference for what sources exist.
    ``citation_required`` controls behaviour when no citations are found:
    - True (default): missing citations is a scored failure (score 0).
    - False: with no citations the criterion does not apply, and the result is errored.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    source_materials: tuple[NonEmptyText, ...] = Field(
        min_length=1,
        description="Descriptions of the actual source materials to check citations against.",
    )
    citation_required: bool = Field(
        default=True,
        description=(
            "Whether attribution is required. True: missing citations is a scored "
            "failure. False: with no citations the criterion does not apply."
        ),
    )

    @field_validator("source_materials")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class AttributionAccuracyGrader(Grader[AttributionAccuracyArgs]):
    """Assess whether citations correctly identify evidence that supports claims.

    Claims can be supported but incorrectly cited. When ``citation_required=True``
    (default), missing citations is a scored failure. When False, evidence with no
    citations is errored, with the judge's reason. Correct source naming is distinct
    from claim support.
    """

    args_model = AttributionAccuracyArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.ATTRIBUTION_ACCURACY,
        scopes=(Scope.TRACE, Scope.ARTIFACT),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        citation_policy = (
            "Attribution is REQUIRED. If the assessed output contains no citations "
            "or source attributions, score 0 — missing required citations is a failure."
            if self.args.citation_required
            else "Attribution is OPTIONAL. If the assessed output contains no citations "
            "or source attributions, the criterion does not apply."
        )
        return (
            "You are assessing whether stated citations or source attributions in the "
            "assessed output correctly identify evidence that supports the associated "
            "claims."
            + section("source_materials", self.args.source_materials)
            + f"\n\n<citation_policy>\n{citation_policy}\n</citation_policy>"
            "\n\n<assessment_boundaries>\n"
            "Assess whether each citation correctly identifies the source material that "
            "supports the associated claim. Correct source naming (pointing to the right "
            "document) is distinct from whether the evidence actually supports the claim "
            "(Claim Support by Evidence). Claims can be supported but incorrectly cited, "
            "and correctly cited but unsupported."
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
