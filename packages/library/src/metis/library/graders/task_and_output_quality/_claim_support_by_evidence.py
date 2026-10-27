"""ClaimSupportByEvidenceGrader: whether claims are supported by designated evidence."""

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


class ClaimSupportByEvidenceArgs(JudgeArgs, TraceArgs, ArtifactArgs):
    """Settings for the claim-support-by-evidence assessment.

    ``designated_evidence`` is the authoritative reference: the judge checks whether
    claims in the assessed output are supported by these passages.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    designated_evidence: tuple[NonEmptyText, ...] = Field(
        min_length=1,
        description="Evidence passages to check the output's claims against.",
    )

    @field_validator("designated_evidence")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class ClaimSupportByEvidenceGrader(Grader[ClaimSupportByEvidenceArgs]):
    """Assess whether claims in the output are supported by designated evidence.

    Support by evidence is independent of whether the claims are true in the world
    and of whether the evidence source is suitable. Evidence with no factual claims to
    check is errored, with the judge's reason.
    """

    args_model = ClaimSupportByEvidenceArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.CLAIM_SUPPORT_BY_EVIDENCE,
        scopes=(Scope.TRACE, Scope.ARTIFACT),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether claims in the assessed output are supported by "
            "the designated evidence."
            + section("designated_evidence", self.args.designated_evidence)
            + "\n\n<assessment_boundaries>\n"
            "Assess whether each claim in the assessed output is actually supported by "
            "the designated evidence above — not merely non-contradicted. A supported "
            "claim need not be true in the world; support and truth are independent. "
            "Whether the evidence source is authoritative, relevant, or current is a "
            "separate concern (Evidence Source Suitability). An omission of essential "
            "source meaning is Content Fidelity, not lack of support. Assess attribution "
            "separately when required.\n\n"
            "If the assessed output contains no factual claims that can be checked "
            "against the designated evidence, the criterion does not apply."
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
