"""LanguageIdentificationAccuracyGrader: whether languages in the input are correctly identified."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field, field_validator

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import judge, section
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


class LanguageIdentificationAccuracyArgs(JudgeArgs, TraceArgs):
    """Settings for the language-identification-accuracy assessment.

    ``expected_languages`` is the authoritative reference for which languages
    are present in the input.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    expected_languages: tuple[NonEmptyText, ...] = Field(
        min_length=1,
        description="The correct language(s) present in the input.",
    )

    @field_validator("expected_languages")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class LanguageIdentificationAccuracyGrader(
    Grader[LanguageIdentificationAccuracyArgs],
):
    """Assess whether the languages present in the input are correctly identified.

    Compares the agent's language identification against expected languages.
    Treats common language aliases as equivalent. Works on text or transcribed
    audio input. Following a requested output language is task constraint
    adherence, not language identification.
    """

    args_model = LanguageIdentificationAccuracyArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.LANGUAGE_IDENTIFICATION_ACCURACY,
        scopes=(Scope.TRACE,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether the language or languages present in the input "
            "were correctly identified by the agent."
            + section("expected_languages", self.args.expected_languages)
            + "\n\n<assessment_boundaries>\n"
            "Assess whether the agent's language identification matches the expected "
            "languages listed above. Treat common language aliases as equivalent (e.g., "
            "'Mandarin' and 'Chinese (Mandarin)' match 'Mandarin Chinese'). For "
            "multilingual input, the agent should identify all expected languages. "
            "Missing an expected language is a failure. Identifying an extra language "
            "not in the expected list is also a failure. Use the input available at "
            "the decision time. Following a requested output language belongs to task "
            "constraint adherence, not language identification."
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
