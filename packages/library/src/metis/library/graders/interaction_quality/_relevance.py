"""RelevanceGrader: the assistant's replies address what the user needs."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem, render_session
from metis.library.grader import Grader, JudgeArgs
from metis.library.judge import judge
from metis.library.scope import SCOPE_DEFINITIONS, SubsessionArgs
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

_CRITERIA = (
    "You are grading relevance: whether the assistant's replies address what the user "
    "needed. A reply is relevant when it responds to the user's current message, given what "
    "came before. A needed question, a stated limit, or a short reply to a greeting can be "
    "relevant. A reply is not relevant when it ignores, misreads, or wanders from what the "
    "user asked. When judging a whole conversation, a few replies that drift do not fail it "
    "if the conversation as a whole stays on the user's needs. Score 1 for relevant and 0 for "
    "not relevant. Do not judge whether a reply is true, complete, or achieves the task."
)


class RelevanceArgs(JudgeArgs, SubsessionArgs):
    purpose: NonEmptyText | None = Field(
        default=None,
        description=(
            'What the assistant is for, such as "answers billing questions for a telecom '
            'provider". The judge uses it to tell which requests the assistant should '
            "handle and which it should redirect."
        ),
    )


class RelevanceGrader(Grader[RelevanceArgs]):
    """Whether the assistant's replies address what the user needs.

    At session scope, by default, one holistic verdict: a few off-target turns can still pass
    when the conversation as a whole stays on the user's needs. At subsession scope, one
    verdict for each turn, judged with the turns before it. Relevance only, not truth,
    completeness or task success. The criteria draw on DeepEval Turn Relevancy and Answer
    Relevancy.
    """

    args_model = RelevanceArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.RELEVANCE,
        scopes=(Scope.SESSION, Scope.SUBSESSION),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        if self.args.purpose is None:
            return _CRITERIA
        return (
            f"{_CRITERIA} The operator states that the assistant is for: "
            f"{self.args.purpose} A reply that redirects or declines a request outside "
            "that purpose is relevant."
        )

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        selected = SCOPE_DEFINITIONS[self.scope].select(input, self.args)
        if isinstance(selected, Problem):
            return GradingOutput.errored(selected.detail)
        return GradingOutput(
            results=[
                await judge(self, llm, label, render_session(turns), self.criteria())
                for label, turns in selected.items()
            ]
        )
