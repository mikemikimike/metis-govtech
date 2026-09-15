"""Enrich a downloaded Artifact with a digest and LLM-written descriptions.

Called once per downloaded artifact per turn by the orchestrator. Always
computes a SHA-256 ``digest`` (cheap; enables future de-dup). For readable,
size-capped text files it asks the user-agent LLM for a **fact-rich**
``content_description`` and a ``state_description``. Binary, oversized, or
unreadable files degrade to a non-LLM description. It never raises into the
turn loop.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from pathlib import Path
from pydantic import BaseModel

from metis.core import Artifact, uri_to_local_path
from metis.core.logging import get_logger

from .user_agent.config import (
    USER_AGENT_API_KEY,
    USER_AGENT_BASE_URL,
    USER_AGENT_MAX_TOKENS,
    USER_AGENT_MODEL,
    USER_AGENT_TEMPERATURE,
)

logger = get_logger()

_MAX_SUMMARIZE_BYTES = 200_000
_TEXT_SUFFIXES = {
    ".csv",
    ".tsv",
    ".txt",
    ".md",
    ".json",
    ".py",
    ".log",
    ".yaml",
    ".yml",
    ".html",
    ".xml",
}

_SUMMARIZER_SYSTEM = (
    "You describe a file that an AI assistant just delivered to a user, for "
    "another AI that role-plays the user. Produce a FACT-RICH content "
    "description: for tabular data give row and column counts and headline "
    "totals/key figures; for text give the headings and the key claims; for "
    "code give what the script does and its inputs/outputs. Be specific with "
    "numbers. Do NOT be vague (never just 'this is a CSV of sales'). Also give "
    "a one-line state description of when/why it was delivered, using the turn "
    "number and the user's triggering message."
)


class _SummaryOut(BaseModel):
    content_description: str
    state_description: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def _summarize_via_llm(
    text: str, *, name: str, triggering_message: str, turn_number: int
) -> tuple[str, str]:
    """Return ``(content_description, state_description)`` from the LLM."""
    client = AsyncOpenAI(api_key=USER_AGENT_API_KEY, base_url=USER_AGENT_BASE_URL)
    user = (
        f"File name: {name}\n"
        f"Delivered on turn {turn_number}.\n"
        f"User's triggering message: {triggering_message!r}\n\n"
        f"File content (may be truncated):\n{text}"
    )
    kwargs: dict[str, object] = dict(
        model=USER_AGENT_MODEL,
        messages=[
            {"role": "system", "content": _SUMMARIZER_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format=_SummaryOut,
    )
    if USER_AGENT_MAX_TOKENS is not None:
        kwargs["max_tokens"] = USER_AGENT_MAX_TOKENS
    if USER_AGENT_TEMPERATURE is not None:
        kwargs["temperature"] = USER_AGENT_TEMPERATURE
    response = await client.beta.chat.completions.parse(**kwargs)
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("summarizer LLM returned an unparseable response")
    return parsed.content_description, parsed.state_description


async def summarize_artifact(
    artifact: Artifact, *, triggering_message: str, turn_number: int
) -> None:
    """Enrich ``artifact`` in place. Never raises."""
    path = uri_to_local_path(artifact.uri)
    if path is None or not path.is_file():
        return

    try:
        artifact.digest = _sha256(path)
        artifact.hash_algorithm = "SHA256"
    except OSError as exc:
        logger.warning(
            "[artifact-summarizer] digest failed for %s: %s", artifact.name, exc
        )

    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    suffix = path.suffix.lower()
    if suffix not in _TEXT_SUFFIXES or size > _MAX_SUMMARIZE_BYTES:
        artifact.content_description = (
            f"binary or oversized {suffix or 'file'}, {size} bytes, not text-summarized"
        )
        artifact.state_description = f"delivered at turn {turn_number}"
        return

    try:
        text = path.read_text(errors="replace")[:_MAX_SUMMARIZE_BYTES]
    except OSError as exc:
        logger.warning(
            "[artifact-summarizer] read failed for %s: %s", artifact.name, exc
        )
        artifact.content_description = f"unreadable {suffix} file, {size} bytes"
        artifact.state_description = f"delivered at turn {turn_number}"
        return

    try:
        content_desc, state_desc = await _summarize_via_llm(
            text,
            name=artifact.name,
            triggering_message=triggering_message,
            turn_number=turn_number,
        )
        artifact.content_description = content_desc
        artifact.state_description = state_desc
    except Exception as exc:  # never propagate into the turn loop
        logger.warning(
            "[artifact-summarizer] LLM summary failed for %s: %s", artifact.name, exc
        )
        artifact.content_description = (
            f"{suffix or 'text'} file, {size} bytes (auto-summary unavailable)"
        )
        artifact.state_description = f"delivered at turn {turn_number}"
