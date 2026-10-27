"""InputInterpretationAccuracyGrader: whether the agent correctly captured the input's meaning."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, field_validator

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import judge, section
from metis.library.scope import SCOPE_DEFINITIONS
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


class InputInterpretationAccuracyArgs(JudgeArgs):
    """Settings for the input-interpretation-accuracy assessment.

    ``interpretation_criteria`` is the authoritative list of aspects to check. The judge
    sees the whole session, so it can see both the user input and the agent's observable
    interpretation.
    """

    interpretation_criteria: tuple[NonEmptyText, ...] = Field(
        min_length=1,
        description="Aspects of interpretation to assess against the input.",
    )

    @field_validator("interpretation_criteria")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class InputInterpretationAccuracyGrader(Grader[InputInterpretationAccuracyArgs]):
    """Assess whether the agent's observable interpretation captured the input's meaning.

    Evaluates the interpretation itself, not the final outcome. Does not infer
    misunderstanding solely from an incorrect result. Does not use later corrections
    to judge an earlier interpretation.
    """

    args_model = InputInterpretationAccuracyArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.INPUT_INTERPRETATION_ACCURACY,
        scopes=(Scope.SESSION,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether the agent's observable interpretation correctly "
            "captures task-relevant information or meaning from the available input."
            + section("interpretation_criteria", self.args.interpretation_criteria)
            + "\n\n<assessment_boundaries>\n"
            "Assess observable interpretation: what the agent demonstrably understood "
            "from the input, as shown in its responses, restatements, extracted "
            "requirements, or identified intent. Do not infer misunderstanding solely "
            "from an incorrect final result. Do not infer unobserved internal "
            "understanding. Do not use later corrections or revised responses to judge "
            "an earlier interpretation — assess each interpretation using only the "
            "information available at the time it was made. Use downstream criteria to "
            "assess the resulting answer or action, and prefer a narrower interpretation "
            "criterion when appropriate."
            "\n</assessment_boundaries>"
            "\n\nThe evidence shows both the user input and the agent's interpretation. "
            "Assess how the agent interpreted the input, not whether the final answer "
            "is correct."
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
