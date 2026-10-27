"""Shared structured-output LLM call and transcript rendering for graders.

This module provides:

- ``judge_call``: the structured-output LLM call used by all LLM-based graders.
- ``render_transcript_with_tool_results``: transcript renderer including tool results.
- ``get_session_turns``: session turns with error handling.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel  # noqa: TC002 — used at runtime in judge_call

from metis.core.grading import GraderResult, GradingOutput
from metis.core.trace_processing import (
    Problem,
    Turn,
    select_all,
    tool_result,
    turns,
)
from metis.library.grader import input_budget_error

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import JudgeArgs, LLMSettings


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------

_SHOWN_PROBLEM = "[unreadable: {kind}: {detail}]"


def _shown_tool_result(observation: object) -> str:
    from metis.core.traces import Observation

    if not isinstance(observation, Observation):
        return ""
    result = tool_result(observation)
    if isinstance(result, Problem):
        return _SHOWN_PROBLEM.format(kind=result.kind, detail=result.detail)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, default=str)
    return result


def render_transcript_with_tool_results(session_turns: tuple[Turn, ...]) -> str:
    """Like ``render_transcript`` but includes tool results after each tool call.

    ``render_transcript`` shows tool arguments only. This helper adds the tool result
    so the judge sees outcome evidence (API responses, state confirmations) that prove
    whether actions actually happened.
    """
    from metis.core.trace_processing import tool_arguments

    blocks: list[str] = []
    for turn in session_turns:
        user = (
            turn.user
            if isinstance(turn.user, str)
            else _SHOWN_PROBLEM.format(kind=turn.user.kind, detail=turn.user.detail)
        )
        lines = [f"## Turn {turn.index + 1}", f"User: {user}"]
        for call in turn.tool_calls:
            args = tool_arguments(call.observation)
            args_text = (
                json.dumps(args, ensure_ascii=False, default=str)
                if isinstance(args, dict)
                else _SHOWN_PROBLEM.format(kind=args.kind, detail=args.detail)
            )
            agent = f" ({call.agent})" if call.agent else ""
            lines.append(f"Tool {call.name}{agent}: {args_text}")
            result_text = _shown_tool_result(call.observation)
            if result_text:
                lines.append(f"Tool result: {result_text}")
        reply = (
            turn.reply
            if isinstance(turn.reply, str)
            else _SHOWN_PROBLEM.format(kind=turn.reply.kind, detail=turn.reply.detail)
        )
        lines.append(f"Assistant: {reply}")
        lines.extend(f"[target error: {error.message}]" for error in turn.target_errors)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def get_session_turns(
    input: GradingInput,
    *,
    evidence_required: bool = True,
) -> tuple[Turn, ...] | GradingOutput:
    """Build turns from input. Returns an errored/skipped output when the session is empty.

    When ``evidence_required`` is True (default), an empty session produces errored
    because the required evidence is unavailable. When False, it produces skipped.
    """
    session = select_all(turns(input))
    if isinstance(session, Problem):
        if evidence_required:
            return GradingOutput(
                results=[
                    GraderResult(
                        status="errored",
                        reason="The session has no turns; required evidence is unavailable.",
                    )
                ]
            )
        return GradingOutput(
            results=[GraderResult(status="skipped", reason="The session has no turns.")]
        )
    return session


# ---------------------------------------------------------------------------
# Structured-output LLM call
# ---------------------------------------------------------------------------


async def judge_call(
    llm: LLMSettings,
    args: JudgeArgs,
    system_prompt: str,
    evidence: str,
    response_model: type[BaseModel],
    schema_name: str,
    *,
    scope: str | None = None,
) -> BaseModel | GraderResult:
    """Make one structured-output judge call and return the parsed response or an error.

    Returns an instance of ``response_model`` on success, or an errored ``GraderResult``
    on any failure (budget exceeded, LLM error, refusal, malformed response).
    ``scope`` is carried on the error result so callers can identify which scope failed.
    """
    request: dict[str, Any] = dict(
        model=args.model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": evidence,
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": response_model.model_json_schema(),
            },
        },
    )
    if over_budget := input_budget_error(args, request):
        return GraderResult(
            status=over_budget.status,
            score=over_budget.score,
            reason=over_budget.reason,
            scope=scope,
        )
    try:
        response = await llm.client.chat.completions.create(**request)
        choice = response.choices[0]
        if choice.finish_reason != "stop" or choice.message.refusal:
            raise ValueError("The judge did not return a complete assessment.")
        return response_model.model_validate_json(choice.message.content or "")
    except Exception as exc:
        return GraderResult(
            status="errored",
            reason=f"Judge failed: {type(exc).__name__}: {exc}",
            scope=scope,
        )
