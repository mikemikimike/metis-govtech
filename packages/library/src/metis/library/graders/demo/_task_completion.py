"""DemoTaskCompletionGrader: by the end of the session, the user got what they asked for."""

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
    "You are grading an assistant over a whole conversation. Collect everything the user asked "
    "for across all turns, then judge how fully the assistant delivered it by the end. Count a "
    "limit the assistant explained and an alternative the user accepted as delivered."
)


class DemoTaskCompletionGrader(Grader[JudgeArgs]):
    """Demo: one judged result for the whole session.

    Shows the session pattern: every turn in order through ``render_transcript``, including the
    tool calls inside them, because the evidence for an earlier request often sits in an earlier
    turn. It lists the run's files in the prompt but does not open them: a real grader would read
    the file ``find_artifacts`` returns. With no files it says so in its reason.
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
        files = sorted({a.name for a in input.artifacts if a.source == "target"})
        transcript = render_transcript(session)
        if files:
            transcript += "\n\nFiles the run produced: " + ", ".join(files)
        verdict = await ask(llm, self.args.model, _INSTRUCTION, transcript)
        if isinstance(verdict, Problem):
            return GradingOutput(
                results=[GraderResult(status="errored", reason=verdict.detail)]
            )
        score, reasoning = verdict
        note = (
            f" Files listed, not opened: {', '.join(files)}."
            if files
            else " No file was checked: the run recorded no artifacts."
        )
        return GradingOutput(
            results=[
                GraderResult(status="scored", score=score, reason=reasoning + note)
            ]
        )
