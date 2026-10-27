"""PlanningQualityGrader: whether the proposed sequence of actions is feasible and sufficient."""

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


class PlanningQualityArgs(JudgeArgs, TaskArgs):
    """Settings for the planning-quality assessment.

    ``task_description`` provides the goal context. ``plan_requirements`` optionally
    specifies aspects to assess such as feasibility, ordering, or dependency handling.
    """

    plan_requirements: tuple[str, ...] = Field(
        default=(),
        description=(
            "Specific aspects to assess such as feasibility, sufficiency, ordering, "
            "or dependency handling. When empty, the judge assesses general plan quality."
        ),
    )

    @field_validator("plan_requirements")
    @classmethod
    def _no_blank_items(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        blanks = [i for i, s in enumerate(v) if not s.strip()]
        if blanks:
            raise ValueError(f"Blank entries at positions {blanks}.")
        return v


class PlanningQualityGrader(Grader[PlanningQualityArgs]):
    """Assess whether the proposed sequence of actions is feasible and sufficient.

    Evaluates the observable plan for feasibility, sufficiency, ordering, and
    dependency handling. A plan need not expose an argument for this assessment. A
    session with no observable plan is errored, with the judge's reason.
    """

    args_model = PlanningQualityArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.PLANNING_QUALITY,
        scopes=(Scope.SESSION,),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        return (
            "You are assessing whether the proposed sequence of actions is feasible "
            "and sufficient to reach the goal."
            + self.args.task_block()
            + section("plan_requirements", self.args.plan_requirements)
            + "\n\n<assessment_boundaries>\n"
            "Assess feasibility, sufficiency, ordering, or dependencies from the "
            "observable plan. A plan need not expose an argument. Do not assess "
            "whether the plan's reasoning is logically valid; only assess whether "
            "the proposed actions are feasible and sufficient. If the session "
            "contains no observable plan or sequence of proposed actions, the "
            "criterion does not apply."
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
