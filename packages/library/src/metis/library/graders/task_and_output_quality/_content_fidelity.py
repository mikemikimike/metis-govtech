"""ContentFidelityGrader: whether a transformation preserves designated source meaning."""

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


class ContentFidelityArgs(JudgeArgs, TraceArgs, ArtifactArgs):
    """Settings for the content-fidelity assessment.

    ``source_content`` is the authoritative source to check preservation against.
    ``fidelity_requirements`` optionally specifies coverage, addition, or omission rules.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    source_content: NonEmptyText = Field(
        description="The designated source content to check preservation against.",
    )
    fidelity_requirements: tuple[str, ...] = Field(
        default=(),
        description=(
            "Specific requirements about coverage, additions, or omissions. "
            "When empty, the judge assesses general meaning preservation."
        ),
    )

    @field_validator("fidelity_requirements")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class ContentFidelityGrader(Grader[ContentFidelityArgs]):
    """Assess whether a transformation preserves the designated source meaning.

    Compares preservation against the source content, not truth against the world.
    A transformation can have supported claims yet lose essential meaning through
    omission. Legitimate omission failures are not suppressed.
    """

    args_model = ContentFidelityArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.CONTENT_FIDELITY,
        scopes=(Scope.TRACE, Scope.ARTIFACT),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether a transformation preserves the designated source "
            "meaning or content."
            f"\n\n<source_content>\n{self.args.source_content}\n</source_content>"
            + section("fidelity_requirements", self.args.fidelity_requirements)
            + "\n\n<assessment_boundaries>\n"
            "Compare preservation against the source, not truth against the world. "
            "A summary can have fully supported claims yet lose essential meaning through "
            "omission. Assess whether the assessed output preserves the source's main "
            "meaning and qualifications, including required coverage and restrictions on "
            "additions or omissions. A legitimate omission failure should not be "
            "suppressed merely because completeness is a related criterion — this "
            "criterion checks preservation relative to the source."
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
