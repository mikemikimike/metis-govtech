"""CommunicationClarityGrader: the assistant's replies are clear and well organized."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from metis.core.grading import GradingOutput
from metis.core.trace_processing import Problem, render_dialogue
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
    "You are grading communication clarity: whether the user can get the meaning of the "
    "assistant's replies without avoidable effort. Check that the main point or answer comes "
    "first or is easy to find; that the order and structure, such as steps, lists, or "
    "headings, fit the content; that the meaning has one reasonable reading; that terms the "
    "user may not know are explained or avoided; and that the point is not hidden under "
    "repetition, filler, or detail the user did not need. Score 1 when the replies are clear. "
    "Score 0 when a reply is ambiguous, disorganized, or padded enough to make the meaning "
    "hard to get. Grammar and natural phrasing belong to output naturalness, and politeness "
    "and warmth to tone, so do not judge them here. Do not judge correctness or task success."
)


class CommunicationClarityArgs(JudgeArgs, SubsessionArgs):
    audience: NonEmptyText | None = Field(
        default=None,
        description=(
            'Who receives the output and what they already know, such as "members of the '
            'public with no technical background". When unset, the judge reads the '
            "audience from the conversation."
        ),
    )


class CommunicationClarityGrader(Grader[CommunicationClarityArgs]):
    """Whether the assistant's replies are clear, well organized and free of avoidable ambiguity.

    At session scope, by default, one verdict on all replies. At subsession scope, one verdict
    for each reply. The judge reads the user messages and the replies, without tool traffic,
    because clarity is a property of what the user reads. It covers organization, ambiguity
    and padding, not fluent phrasing or tone, which have their own graders. The criteria draw
    on Phoenix conciseness.
    """

    args_model = CommunicationClarityArgs
    taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
        measure=Measure.COMMUNICATION_CLARITY,
        scopes=(Scope.SESSION, Scope.SUBSESSION),
        grader_types=(GraderType.LLM,),
        reference_types=(ReferenceType.RUBRIC_BASED,),
        judgment_forms=(JudgmentForm.BINARY,),
        aggregations=(Aggregation.NONE_SINGLE_SCORE,),
    )

    def criteria(self) -> str:
        if self.args.audience is None:
            return _CRITERIA
        return (
            f"{_CRITERIA} Judge clarity for this audience, not for the user that the "
            f"conversation suggests: {self.args.audience} Count a term as unexplained only "
            "if this audience would not know it."
        )

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        selected = SCOPE_DEFINITIONS[self.scope].select(input, self.args)
        if isinstance(selected, Problem):
            return GradingOutput.errored(selected.detail)
        return GradingOutput(
            results=[
                await judge(self, llm, label, render_dialogue(turns), self.criteria())
                for label, turns in selected.items()
            ]
        )
