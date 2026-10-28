"""ToolChoiceAppropriatenessGrader: whether the selected tool is suitable."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import TaskArgs, ToolListArgs, judge, section
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


class ToolChoiceAppropriatenessArgs(JudgeArgs, TaskArgs, ToolListArgs):
    """Settings for the tool-choice appropriateness assessment.

    ``task_description`` provides the goal context. The tool list lets the judge assess
    whether an available alternative better fits the task and whether unused tools should
    have been used.
    """


class ToolChoiceAppropriatenessGrader(Grader[ToolChoiceAppropriatenessArgs]):
    """Assess whether the selected tool is suitable for the task.

    Evaluates tool suitability, including whether a tool is needed at all and
    whether an available alternative better fits the task. A session with no recorded
    tool calls is judged too: it fails when the task needed a tool, and passes when it
    did not. Tool arguments are assessed separately.

    Requires a tool list: the ``available_tools`` setting, or the tools the session
    offered. With neither, the result is errored without a judge call.
    """

    args_model = ToolChoiceAppropriatenessArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.TOOL_CHOICE_APPROPRIATENESS,
        scopes=(Scope.SESSION,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self, tools: tuple[str, ...]) -> str:
        return (
            "You are assessing whether the selected tool is suitable for the "
            "immediate objective and available conditions."
            + self.args.task_block()
            + section("available_tools", tools)
            + "\n\n<assessment_boundaries>\n"
            "The available_tools list above is the complete set the agent could "
            "choose from. Assess tool suitability against this list, including "
            "whether a tool call is needed at all and whether an available "
            "alternative better fits the task. Do not assume the trace shows every "
            "available tool — tools that were available but unused may still be "
            "the better choice. Arguments are assessed separately."
            "\n</assessment_boundaries>"
        )

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        tools = self.args.tool_list(input.traces)
        if not tools:
            return GradingOutput.errored(
                "No tool list: set available_tools, or record the tools the agent was "
                "offered."
            )
        scope = SCOPE_DEFINITIONS[self.scope]
        selected = scope.select(input, self.args)
        if isinstance(selected, Problem):
            return GradingOutput.errored(selected.detail)
        return GradingOutput(
            results=[
                await judge(
                    self,
                    llm,
                    label,
                    scope.render(thing),
                    self.criteria(tools),
                )
                for label, thing in selected.items()
            ]
        )
