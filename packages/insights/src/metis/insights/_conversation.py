"""A trial's conversation for the report, read from the traces `evaluate` saved (#462).

`metis engine evaluate` writes each session's traces to ``outputs/traces/`` as the Langfuse rows
(``SessionTraces``). The report reads them back and lets ``metis.core.trace_processing`` turn
them into turns, so it never touches Langfuse and shows what the graders read. A file that is
missing, unreadable or for another session gives a ``Problem``, never an exception, so one bad
file cannot stop a report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from metis.core import SessionTraces, execution_layout
from metis.core.trace_processing import Problem, turns

if TYPE_CHECKING:
    from pathlib import Path

    from metis.core.trace_processing import Turn


def _unreadable(path: Path, exc: ValueError | OSError) -> Problem:
    """A short reason. For a pydantic error the useful text is in ``errors()``, not ``str``."""
    if isinstance(exc, ValidationError):
        reason = exc.errors()[0]["msg"]
    else:
        reason = str(exc) or type(exc).__name__
    return Problem(kind="unsupported", detail=f"cannot read {path.name}: {reason}")


def read_turns(experiment_dir: Path, session_id: str) -> tuple[Turn, ...] | Problem:
    """The session's turns from its saved traces, or why they are unavailable."""
    path = (
        experiment_dir
        / execution_layout.TRACES
        / execution_layout.trace_file_name(session_id)
    )
    try:
        saved = SessionTraces.load_file(path)
    except FileNotFoundError:
        return Problem(kind="missing", detail=f"no saved traces at {path}")
    except (OSError, ValueError) as exc:
        return _unreadable(path, exc)
    if saved.session_id != session_id:
        return Problem(
            kind="unsupported",
            detail=(
                f"{path.name} holds session {saved.session_id!r}, not {session_id!r}"
            ),
        )
    try:
        return turns(saved.to_traces())
    except ValueError as exc:
        return _unreadable(path, exc)


def _shown(value: str | Problem) -> str:
    """Text as shown, or a visible marker where METIS could not read it."""
    if isinstance(value, Problem):
        return f"[unreadable: {value.kind}: {value.detail}]"
    return value


def conversation_rows(session_turns: tuple[Turn, ...]) -> list[dict[str, object]]:
    """One ``{turn, user, target, errors}`` row per turn; ``turn`` counts from 1."""
    return [
        {
            "turn": turn.index + 1,
            "user": _shown(turn.user),
            "target": _shown(turn.reply),
            "errors": [error.message for error in turn.target_errors],
        }
        for turn in session_turns
    ]


def turn_count_note(saved: int, recorded: int | None) -> str | None:
    """A note when fewer turns have traces than the record counted, else ``None``.

    A message METIS withheld never reaches the target, so it leaves no trace; a gap here is the
    only visible sign of it.
    """
    if recorded is None or saved == recorded:
        return None
    return f"{saved} of {recorded} recorded turns have traces"
