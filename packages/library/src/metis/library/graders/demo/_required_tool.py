"""DemoRequiredToolGrader: the target called a given tool somewhere in the session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from metis.core.grading import GraderResult, GradingOutput
from metis.core.trace_processing import Problem, select_all, select_where, turns
from metis.library.grader import Grader, GraderArgs

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import LLMSettings


class DemoRequiredToolArgs(GraderArgs):
    tool_name: str = Field(min_length=1)
    """The name of the tool call the session must contain, exactly as traced."""


class DemoRequiredToolGrader(Grader[DemoRequiredToolArgs]):
    """Demo: the target made a ``tool_name`` call at least once.

    Shows the tool-call view: every ``TOOL`` observation at any depth, so a call a sub-agent
    made several levels down still counts, and ``select_where`` to pick calls by name.
    Code-based and session-scoped: 1.0 if found, else 0.0. Skips a session with no turns.
    """

    args_model = DemoRequiredToolArgs

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        session = select_all(turns(input.traces))
        if isinstance(session, Problem):
            return GradingOutput(
                results=[
                    GraderResult(status="skipped", reason="The session has no turns.")
                ]
            )
        calls = tuple(call for turn in session for call in turn.tool_calls)
        name = self.args.tool_name
        matches = select_where(calls, lambda call: call.name == name)
        if isinstance(matches, Problem):
            result = GraderResult(
                status="scored",
                score=0.0,
                reason=f"No {name} call in {len(calls)} tool call(s) across {len(session)} turn(s).",
            )
        else:
            first = matches[0]
            by = f" by {first.agent}" if first.agent else ""
            result = GraderResult(
                status="scored",
                score=1.0,
                reason=f"{name} was called {len(matches)} time(s), first in turn "
                f"{first.turn_index + 1}{by}.",
            )
        return GradingOutput(results=[result])
