"""ToolArgumentCorrectnessGrader: whether submitted tool parameters are valid and aligned."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, field_validator

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem, turns
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


class ToolArgumentCorrectnessArgs(JudgeArgs, TaskArgs):
    """Settings for the tool-argument correctness assessment.

    ``task_description`` provides the goal context. ``argument_requirements``
    optionally specifies syntactic or semantic requirements for tool parameters.
    """

    argument_requirements: tuple[str, ...] = Field(
        default=(),
        description=(
            "Specific syntactic or semantic requirements for tool parameters. "
            "When empty, the judge assesses general argument correctness."
        ),
    )

    @field_validator("argument_requirements")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class ToolArgumentCorrectnessGrader(Grader[ToolArgumentCorrectnessArgs]):
    """Assess whether submitted tool parameters are valid and semantically aligned.

    Evaluates syntactic validity and semantic appropriateness of tool arguments.
    Tool selection is assessed separately. A session with no recorded tool calls is
    errored.
    """

    args_model = ToolArgumentCorrectnessArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.TOOL_ARGUMENT_CORRECTNESS,
        scopes=(Scope.SESSION,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether submitted tool parameters are valid and "
            "semantically aligned with the intended action."
            + self.args.task_block()
            + section("argument_requirements", self.args.argument_requirements)
            + "\n\n<assessment_boundaries>\n"
            "Assess syntactic validity and semantic appropriateness of submitted "
            "parameters. Tool selection is a separate criterion."
            "\n</assessment_boundaries>"
        )

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        scope = SCOPE_DEFINITIONS[self.scope]
        selected = scope.select(input, self.args)
        if isinstance(selected, Problem):
            return GradingOutput.errored(selected.detail)
        if not any(turn.tool_calls for turn in turns(input.traces)):
            return GradingOutput.errored(
                "The session has no recorded tool calls, so tool argument correctness "
                "cannot be assessed."
            )
        return GradingOutput(
            results=[
                await judge(self, llm, label, scope.render(thing), self.criteria())
                for label, thing in selected.items()
            ]
        )
