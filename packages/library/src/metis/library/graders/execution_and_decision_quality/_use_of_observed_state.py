"""UseOfObservedStateGrader: whether actions are justified by available observations."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import TaskArgs, judge
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


class UseOfObservedStateArgs(JudgeArgs, TaskArgs):
    """Settings for the use-of-observed-state assessment.

    ``task_description`` provides the goal context against which the agent's
    use of observations is evaluated.
    """


class UseOfObservedStateGrader(Grader[UseOfObservedStateArgs]):
    """Assess whether actions are justified by available environment observations.

    Evaluates whether each significant action is supported by the observations
    available at that point in the execution. State updates and prior-information
    retrieval are assessed separately.
    """

    args_model = UseOfObservedStateArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.USE_OF_OBSERVED_STATE,
        scopes=(Scope.SESSION,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether actions are justified by the environment "
            "observations available at that moment."
            + self.args.task_block()
            + "\n\n<assessment_boundaries>\n"
            "Judge whether each significant action is justified by observations "
            "available at that point. Do not assess state tracking or retrieval of "
            "prior information; only assess whether available observations justified "
            "the action."
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
