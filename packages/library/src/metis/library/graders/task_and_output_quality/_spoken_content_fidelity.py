"""SpokenContentFidelityGrader: whether delivered speech preserves intended content."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import judge
from metis.library.scope import SCOPE_DEFINITIONS, TraceArgs
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


class SpokenContentFidelityArgs(JudgeArgs, TraceArgs):
    """Settings for the spoken-content-fidelity assessment.

    ``intended_content`` is the text intended for speech generation.
    ``transcript_provenance`` optionally records how the delivered-speech
    transcript was obtained (e.g., 'independent transcription of delivered
    recording'). METIS does not independently verify the audio.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    intended_content: NonEmptyText = Field(
        description="The text content intended for speech generation.",
    )
    transcript_provenance: str = Field(
        default="",
        description=(
            "How the delivered-speech transcript was obtained (e.g., "
            "'independent transcription of delivered recording'). "
            "METIS does not independently verify the audio."
        ),
    )


class SpokenContentFidelityGrader(Grader[SpokenContentFidelityArgs]):
    """Assess whether delivered speech preserves the intended content.

    Speech specialization of content fidelity. Compares an independently supplied
    transcript of delivered speech against the text intended for speech generation.
    The intended content is a script, not evidence of delivery. METIS does not
    independently verify the audio. Human intelligibility, acoustic quality, and
    pronunciation are separate concerns. Transcript-only support in this version.
    """

    args_model = SpokenContentFidelityArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.SPOKEN_CONTENT_FIDELITY,
        scopes=(Scope.TRACE,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        provenance_note = (
            f"\n\nTranscript provenance: {self.args.transcript_provenance}"
            if self.args.transcript_provenance
            else ""
        )
        return (
            "You are assessing whether delivered speech preserves the content intended "
            "for speech generation without unintended omissions, substitutions, or "
            "additions."
            f"\n\n<intended_content>\n{self.args.intended_content}\n</intended_content>"
            + provenance_note
            + "\n\n<assessment_boundaries>\n"
            "Compare the independently supplied transcript of delivered speech (in the "
            "assessed evidence) against the intended content above. The intended content "
            "is a script, NOT evidence that these words were actually spoken. The assessed "
            "evidence must be an independently obtained transcript of the delivered "
            "recording. METIS does not independently verify the audio. "
            "Assess whether the delivered speech preserves the intended words and meaning "
            "without unintended omissions, substitutions, or additions. "
            "Human intelligibility, acoustic quality, and pronunciation are separate "
            "concerns and are not assessed by this grader."
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
