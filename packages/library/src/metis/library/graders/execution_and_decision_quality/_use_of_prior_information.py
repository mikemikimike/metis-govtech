"""UseOfPriorInformationGrader: whether relevant earlier facts are retrieved and applied."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, field_validator

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import TaskArgs, judge, section
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

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import LLMSettings


class UseOfPriorInformationArgs(JudgeArgs, TaskArgs):
    """Settings for the use-of-prior-information assessment.

    ``task_description`` provides the goal context. ``prior_information`` optionally
    specifies earlier facts or instructions that should be retrieved and applied.
    """

    prior_information: tuple[str, ...] = Field(
        default=(),
        description=(
            "Earlier facts, instructions, or experiences that should be retrieved "
            "and applied. When empty, the judge assesses general retrieval and "
            "application of prior information."
        ),
    )

    @field_validator("prior_information")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class UseOfPriorInformationGrader(Grader[UseOfPriorInformationArgs]):
    """Assess whether relevant earlier facts, instructions, or experiences are
    retrieved and applied appropriately.

    Judges retrieval and application of prior information, separate from observing
    or updating current state.
    """

    args_model = UseOfPriorInformationArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.USE_OF_PRIOR_INFORMATION,
        scopes=(Scope.SESSION,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether relevant earlier facts, instructions, or "
            "experiences are retrieved and applied appropriately."
            + self.args.task_block()
            + section("prior_information", self.args.prior_information)
            + "\n\n<assessment_boundaries>\n"
            "Judge retrieval and application of earlier facts and instructions. "
            "Separate from observing or updating current state. Score 1 when no "
            "earlier information is relevant, or when the agent uses it correctly."
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
