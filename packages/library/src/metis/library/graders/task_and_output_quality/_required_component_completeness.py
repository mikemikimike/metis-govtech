"""RequiredComponentCompletenessGrader: whether every required component is present."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal, Self

from pydantic import Field, model_validator

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem
from metis.library.aggregation import AGGREGATION_DEFINITIONS
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import judge
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


class RequiredComponentCompletenessArgs(JudgeArgs, TraceArgs, ArtifactArgs):
    """Settings for the required-component-completeness assessment.

    ``required_components`` is the authoritative list of components. Each component is
    judged on its own, and a result scores 1 only when every component is present. The result
    is errored when no component is missing but one cannot be judged.
    """

    turn: Literal["each", "last"] = "last"
    """``last`` judges only the final reply. ``each`` judges every reply."""
    required_components: tuple[NonEmptyText, ...] = Field(
        min_length=1,
        description="Components that must be present in the assessed evidence.",
    )

    @model_validator(mode="after")
    def _no_duplicate_items(self) -> Self:
        seen: set[str] = set()
        dupes: list[str] = []
        for c in self.required_components:
            normalized = c.strip().lower()
            if normalized in seen:
                dupes.append(c)
            seen.add(normalized)
        if dupes:
            raise ValueError(
                f"Duplicate required components (case-insensitive): {dupes}."
            )
        return self


class RequiredComponentCompletenessGrader(Grader[RequiredComponentCompletenessArgs]):
    """Assess whether every explicitly requested component is present.

    Checks presence only, not correctness or quality. Each component is judged on its own,
    and a result scores 1 only when every component is present. The result scores 0 when any
    component is missing, and is errored when none is missing but one cannot be judged.
    """

    args_model = RequiredComponentCompletenessArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.REQUIRED_COMPONENT_COMPLETENESS,
        scopes=(Scope.TRACE, Scope.ARTIFACT),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.EXPECTED_OUTPUT,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.PASS_IF_ALL,),
    )

    def criteria(self, component: str) -> str:
        return (
            "You are assessing whether one explicitly required component is present "
            "in the assessed evidence."
            f"\n\n<required_component>\n{component}\n</required_component>"
            "\n\n<assessment_boundaries>\n"
            "Assess the PRESENCE of each required component, independently of its "
            "correctness or quality. A component that is present but contains errors "
            "still counts as present. A component that is absent or cannot be identified "
            "is not present, and scores 0."
            "\n</assessment_boundaries>"
        )

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        scope = SCOPE_DEFINITIONS[self.scope]
        selected = scope.select(input, self.args)
        if isinstance(selected, Problem):
            return GradingOutput.errored(selected.detail)
        combine = AGGREGATION_DEFINITIONS[self.aggregation]
        results = []
        for label, thing in selected.items():
            evidence = scope.render(thing)
            per_rule = [
                await judge(self, llm, label, evidence, self.criteria(component))
                for component in self.args.required_components
            ]
            results.append(combine(per_rule, label))
        return GradingOutput(results=results)
