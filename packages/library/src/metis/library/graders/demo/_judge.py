"""The one LLM call the demo judges share: a transcript in, a reasoned 0-1 score out.

A stand-in for #428's structured judge helper, kept private to the demos. Any reply that is not
the expected JSON, and any failure of the call itself, comes back as a ``Problem`` so the
caller records ``errored``, never a score.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from metis.core.trace_processing import Problem

if TYPE_CHECKING:
    from metis.library.grader import LLMSettings

_FORMAT = (
    'Reply with only a JSON object: {"reasoning": "<one or two sentences>", '
    '"score": <a number from 0 to 1>}.'
)


async def ask(
    llm: LLMSettings, model: str, instruction: str, transcript: str
) -> tuple[float, str] | Problem:
    """Asks the judge ``instruction`` about ``transcript``; returns ``(score, reasoning)``."""
    try:
        response = await llm.client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": f"{instruction}\n\n{_FORMAT}"},
                {"role": "user", "content": transcript},
            ],
        )
        content = response.choices[0].message.content or ""
    except Exception as exc:  # any client failure is the grader's, not the target's
        return Problem(kind="unsupported", detail=f"the judge call failed: {exc}")
    try:
        reply = json.loads(content)
    except ValueError:
        return Problem(
            kind="unsupported",
            detail=f"the judge did not reply in JSON: {content[:80]!r}",
        )
    score = reply.get("score") if isinstance(reply, dict) else None
    reasoning = reply.get("reasoning") if isinstance(reply, dict) else None
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not 0 <= score <= 1
        or not isinstance(reasoning, str)
    ):
        return Problem(
            kind="unsupported",
            detail=f"the judge's reply is off-menu: {content[:80]!r}",
        )
    return float(score), reasoning
