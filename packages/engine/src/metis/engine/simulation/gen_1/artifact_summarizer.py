"""Enrich a downloaded Artifact with a digest and LLM-written descriptions.

Called once per downloaded artifact per turn by the orchestrator. Always
computes a SHA-256 ``digest`` (cheap; enables future de-dup). For readable,
size-capped text files it asks the user-agent LLM for a **fact-rich**
``content_description`` and a ``state_description``. Binary, oversized, or
unreadable files degrade to a non-LLM description. It never raises into the
turn loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from metis.core import Artifact, resolve_artifact_path
from metis.core.logging import get_logger
from metis.engine.tracing import traced

from .._fixture_artifacts import build_fixture_artifacts
from .._hashing import sha256_file
from ..llm_calls import LLMCallLog, parse_completion
from ..model_settings import llm_client, sampling_options, user_agent_settings

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from openai.types.chat import ChatCompletionMessageParam

    from metis.core.model_settings import RoleSettings

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
    "totals/key figures; for text give the headings and the key findings and "
    "claims about its own subject matter; for code give what the script does "
    "and its inputs/outputs. Be specific with "
    "numbers. Do NOT be vague (never just 'this is a CSV of sales'). "
    "Describe ONLY what is in this one file. If the file lists, links to, or "
    "claims the existence of other files — a deliverables list, an index, a "
    "manifest of charts — do NOT restate those as files that exist; at most "
    "note that this document refers to other outputs. You are describing this "
    "file's contents, not verifying its claims about other artifacts. Also "
    "give a one-line state description of when/why it was delivered, using "
    "the turn number and the user's triggering message."
)


class _SummaryOut(BaseModel):
    content_description: str
    state_description: str


async def _summarize_via_llm(
    text: str,
    *,
    name: str,
    triggering_message: str,
    turn_number: int,
    llm_log: LLMCallLog,
    settings: RoleSettings,
) -> tuple[str, str]:
    """Return ``(content_description, state_description)`` from the LLM."""
    # Retries go through parse_completion so each attempt is logged.
    client = llm_client(settings)
    user = (
        f"File name: {name}\n"
        f"Delivered on turn {turn_number}.\n"
        f"User's triggering message: {triggering_message!r}\n\n"
        f"File content (may be truncated):\n{text}"
    )
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _SUMMARIZER_SYSTEM},
        {"role": "user", "content": user},
    ]
    response = await parse_completion(
        client,
        llm_log,
        component="artifact_summarizer",
        model=settings.model,
        messages=messages,
        response_format=_SummaryOut,
        **sampling_options(),
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("summarizer LLM returned an unparseable response")
    return parsed.content_description, parsed.state_description


async def summarize_artifact(
    artifact: Artifact,
    *,
    experiment_root: Path,
    triggering_message: str,
    turn_number: int,
    llm_log: LLMCallLog,
    settings: RoleSettings | None = None,
) -> None:
    """Enrich ``artifact`` in place. Never raises.

    :param llm_log: Where the summary call's rows go: the trial's log for a
        download, the experiment's for a fixture.
    :param settings: The user agent role, which the summariser shares. Unset, it
        resolves from the environment.
    """
    if artifact.state != "received":
        return
    path = resolve_artifact_path(experiment_root, artifact.path)
    if path is None or not path.is_file():
        return

    try:
        artifact.digest = sha256_file(path)
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
        text = path.read_text(encoding="utf-8", errors="replace")[:_MAX_SUMMARIZE_BYTES]
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
            llm_log=llm_log,
            settings=settings or user_agent_settings(),
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


async def summarize_fixture_artifacts(
    fixtures: list[Artifact],
    experiment_root: Path,
    *,
    llm_log: LLMCallLog,
    settings: RoleSettings | None = None,
) -> None:
    """Fill ``content_description`` for fixtures the author left undescribed.

    Reuses :func:`summarize_artifact` (the same summarizer target outputs use).
    Its ``state_description`` is target-facing ("delivered at turn N"), which is
    wrong for an uploaded fixture, so it is cleared afterward — fixtures are
    disambiguated for the persona by ``source`` + ``at_simulated_turn``, not a state line.
    Mutates each artifact in place; never raises into the caller.
    """
    for artifact in fixtures:
        if artifact.content_description:
            continue
        await summarize_artifact(
            artifact,
            experiment_root=experiment_root,
            triggering_message="(staged fixture, uploaded by the user)",
            turn_number=0,
            llm_log=llm_log,
            settings=settings,
        )
        artifact.state_description = None


async def resolve_fixture_descriptions(
    fixture_names: Iterable[str],
    fixtures_dir: Path,
    experiment_root: Path,
    author_descriptions: dict[str, str],
    *,
    user_agent_model: str | None = None,
) -> dict[str, str]:
    """Resolve exactly one ``content_description`` per unique fixture, experiment-wide.

    ``user_agent_model`` is the experiment's ``defaults.user_agent_model``. The summaries
    run once for the experiment, so a Test Case model does not apply to them.

    A fixture's content is invariant across the scenarios that reference it, so
    it deserves a single description (spec §6). Author-supplied descriptions win;
    each fixture the author left undescribed is summarized **once here**, before
    workers fan out — not per run and not per attempt. The returned name→description
    map is threaded into every per-run :func:`build_fixture_artifacts` call, so no
    run re-summarizes. Names absent from the map (missing/unreadable on disk) are
    simply omitted. Never raises into the caller. The summaries' LLM calls go to
    the experiment's ``logs/llm_calls.jsonl``, since they belong to no one trial,
    and to one ``fixture_descriptions`` trace in the experiment's Langfuse session.
    """
    unique_names = sorted(set(fixture_names))
    artifacts = build_fixture_artifacts(
        unique_names, fixtures_dir, experiment_root, author_descriptions
    )
    experiment = experiment_root.resolve().name
    await traced(
        lambda: summarize_fixture_artifacts(
            artifacts,
            experiment_root,
            llm_log=LLMCallLog.for_experiment(experiment_root),
            settings=user_agent_settings(user_agent_model),
        ),
        name="fixture_descriptions",
        session_id=experiment,
        metadata={"experiment": experiment},
    )
    return {
        a.name: a.content_description
        for a in artifacts
        if a.content_description is not None
    }
