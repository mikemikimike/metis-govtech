"""Data Analysis Recovery metric (M-DA-26)."""

from typing import Any, ClassVar

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnMetric,
    _ContextAwareGEval,
    mark_skipped,
)
from ._extraction import CODE_TOOLS, tool_calls_named
from ._judge import _get_judge_model

# Substrings that mark an execution error in a code-tool output.
_ERROR_MARKERS = (
    "traceback",
    "error",
    "exception",
    "not defined",
    "failed",
)


def _code_events(test_case: LLMTestCase) -> list[tuple[str, str, bool]]:
    """Ordered (code, output_text, failed) tuples for code-tool calls."""
    events: list[tuple[str, str, bool]] = []
    for tc in tool_calls_named(test_case, *CODE_TOOLS):
        inp = tc.get("input")
        code = ""
        if isinstance(inp, dict):
            code = inp.get("code") or inp.get("script") or inp.get("source") or ""
        elif isinstance(inp, str):
            code = inp
        out = tc.get("output")
        out_text = out if isinstance(out, str) else str(out) if out else ""
        failed = any(m in out_text.lower() for m in _ERROR_MARKERS)
        events.append((str(code), out_text, failed))
    return events


class DataAnalysisRecoveryMetric(MetisTurnMetric):
    """On a failure, did the agent diagnose and stop within <=3 retries?

    Judge-graded (M-DA-26). Applicable only when an ``execute_python`` call
    failed on the turn. Assesses root-cause diagnosis, distinct retries (no
    identical re-runs), and a bounded retry count instead of blind looping.
    Skips when no execution failure is observable.
    """

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Data Analysis Recovery",
                model=_get_judge_model(),
                criteria=(
                    "On an execute_python failure, the agent should identify "
                    "the root cause before retrying, should not re-run "
                    "identical failing code, and should stop after at most "
                    "three retries per error; judge the ordered sequence of "
                    "executed code and its error outputs for root-cause "
                    "diagnosis, distinct (non-identical) retries, and a bounded "
                    "retry count (<=3) rather than blind looping.\n\n"
                    "The 'input' is the user's request; the 'context' holds "
                    "the ordered code executions and their error outputs; the "
                    "'actual_output' is the agent's response.\n\n"
                    "Assess three dimensions:\n"
                    "1. Root-cause diagnosis: Before retrying, does the agent "
                    "read the error and address its cause, rather than blindly "
                    "re-running?\n"
                    "2. No identical re-run: Are retries meaningfully different "
                    "from the code that just failed?\n"
                    "3. Bounded retries: Does it stop after at most three "
                    "retries per error instead of looping indefinitely?\n\n"
                    "Score 1.0 when the agent diagnoses the cause, retries "
                    "differently, and stays within the retry bound. "
                    "Score 0.5 when recovery is partial (e.g. bounded but "
                    "without clear diagnosis). "
                    "Score 0.0 when it re-runs identical failing code or loops "
                    "past three retries without diagnosis." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.CONTEXT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _augmented(self, test_case: LLMTestCase, events: list) -> LLMTestCase:
        lines: list[str] = []
        for i, (code, out_text, failed) in enumerate(events, start=1):
            status = "FAILED" if failed else "ok"
            lines.append(
                f"[execution {i}] status={status}\ncode:\n{code}\n"
                f"output:\n{out_text[:800]}"
            )
        return LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=["Execution sequence:\n\n" + "\n\n".join(lines)],
            metadata=test_case.metadata,
        )

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        events = _code_events(test_case)
        if not any(failed for _, _, failed in events):
            return mark_skipped(
                self,
                "no execute_python failure observed; error recovery is not applicable.",
            )
        geval = self._get_geval()
        await geval.a_measure(self._augmented(test_case, events))
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Data Analysis Recovery"

    def is_successful(self) -> bool:
        return self.success is True
