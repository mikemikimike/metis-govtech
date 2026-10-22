"""DemoAnswerHelpfulnessGrader: each reply helps with what the user just asked."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.core.grading import GraderResult, GradingOutput
from metis.core.trace_processing import Problem, render_transcript, select_all, turns
from metis.library.grader import Grader, JudgeArgs

from ._judge import ask

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import LLMSettings

_INSTRUCTION = (
    "You are grading an assistant. Read the conversation and judge only the assistant's LAST "
    "reply: does it help with the user's LAST message, given what came before? A reply that "
    "asks a needed question or explains a real limit can still be helpful."
)


class DemoAnswerHelpfulnessGrader(Grader[JudgeArgs]):
    """Demo: one judged result per turn, each on that turn plus the turns before it.

    Shows the per-turn pattern: turn ``i`` is judged on ``render_transcript(turns[: i + 1])``,
    so the judge has the context a form response or follow-up needs and never sees what came
    after. A turn whose message or reply METIS could not read is skipped, not scored, unless
    the target itself reported an error on it: a missing reply is the target failing, so that
    turn is judged, with the error shown in the transcript.
    """

    args_model = JudgeArgs

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        session = select_all(turns(input.traces))
        if isinstance(session, Problem):
            return GradingOutput(
                results=[
                    GraderResult(status="skipped", reason="The session has no turns.")
                ]
            )
        results: list[GraderResult] = []
        for turn in session:
            unreadable = next(
                (v for v in (turn.user, turn.reply) if isinstance(v, Problem)), None
            )
            if unreadable is not None and not turn.target_errors:
                results.append(
                    GraderResult(
                        status="skipped",
                        reason=f"Turn {turn.index + 1}: {unreadable.detail}.",
                    )
                )
                continue
            verdict = await ask(
                llm,
                self.args.model,
                _INSTRUCTION,
                render_transcript(session[: turn.index + 1]),
            )
            if isinstance(verdict, Problem):
                results.append(
                    GraderResult(
                        status="errored",
                        reason=f"Turn {turn.index + 1}: {verdict.detail}",
                    )
                )
            else:
                score, reasoning = verdict
                results.append(
                    GraderResult(
                        status="scored",
                        score=score,
                        reason=f"Turn {turn.index + 1}: {reasoning}",
                    )
                )
        return GradingOutput(results=results)
