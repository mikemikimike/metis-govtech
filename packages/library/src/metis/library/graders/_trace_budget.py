"""TraceBudgetGrader: the session stayed within a trace budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from metis.core.grading import GraderResult, GradingOutput
from metis.library.grader import Grader, GraderArgs

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import LLMSettings


class TraceBudgetArgs(GraderArgs):
    max_traces: int = Field(default=10, ge=1, strict=True)
    """The most traces the session may contain and still pass."""


class TraceBudgetGrader(Grader[TraceBudgetArgs]):
    """Session stayed within the allowed number of traces.

    Code-based and session-scoped: counts every trace in the session, including traces whose
    root has no output, and scores 1.0 when the count is at most ``max_traces`` and 0.0
    otherwise. Skips a session with no traces, since there is nothing to count. One trace is
    usually one persona message and the target's reply, so this is a budget on exchanges.
    """

    args_model = TraceBudgetArgs

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        count = len(input.traces)
        budget = self.args.max_traces
        if count == 0:
            result = GraderResult(
                status="skipped", reason="The session has no traces to count."
            )
        else:
            result = GraderResult(
                status="scored",
                score=1.0 if count <= budget else 0.0,
                reason=f"The session used {count} trace(s) against a budget of {budget}.",
            )
        return GradingOutput(results=[result])
