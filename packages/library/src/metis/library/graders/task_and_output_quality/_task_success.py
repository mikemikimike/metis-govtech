"""TaskSuccessGrader: whether the requested end goal was achieved."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, field_validator

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import TaskArgs, judge, section
from metis.library.scope import SCOPE_DEFINITIONS, ArtifactArgs
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


class TaskSuccessArgs(JudgeArgs, ArtifactArgs, TaskArgs):
    """Settings for the task-success assessment.

    ``task_description`` and ``success_conditions`` are the assessment criteria, set in the
    specification. When ``task_description`` is unset, the judge infers the goal from the
    user's messages.
    """

    success_conditions: tuple[str, ...] = Field(
        default=(),
        description=(
            "Observable conditions that define success. When empty, "
            "the judge infers conditions from the task description."
        ),
    )

    @field_validator("success_conditions")
    @classmethod
    def _no_blank_conditions(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank success conditions at positions {blanks}.")
        return v


class TaskSuccessGrader(Grader[TaskSuccessArgs]):
    """Assess whether the requested end goal was achieved under declared success conditions.

    For action tasks, requires recorded outcome evidence (tool results, state changes);
    an agent's claim of completion alone is insufficient. The evidence includes tool
    results so the judge can verify that actions actually happened.
    """

    args_model = TaskSuccessArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.TASK_SUCCESS,
        scopes=(Scope.SESSION, Scope.ARTIFACT),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether the requested end goal was achieved."
            + self.args.task_block()
            + section("success_conditions", self.args.success_conditions)
            + "\n\n<assessment_boundaries>\n"
            "Assess whether the declared end goals and mandatory conditions were achieved. "
            "For action tasks, require recorded outcome evidence such as tool results that "
            "show state changes or confirmations from external systems. An agent's claim of "
            'completion alone (e.g. "I have completed the task") is insufficient without '
            "supporting evidence in tool results or system responses. "
            "For answer-only tasks, a correct and complete answer may establish success."
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
