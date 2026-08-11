"""Where sessions live, and how the door finds them.

There is no database and no index. A session is a `session.json` inside its own directory,
which is exactly what `metis wizard init --out-dir <dir>` already writes — so a session
started in the browser is resumable from the terminal by pointing `--out-dir` at its
directory, and one started in the terminal shows up in the browser list. Two doors, one
directory, nothing to keep in step.

Listing reads each file, which is fine at the scale a local wizard runs at and avoids the
one thing an index would add: a second record of the truth that can go stale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from metis.wizard.contracts.session_state import SessionState

SESSION_FILENAME = "session.json"
UNTITLED = "Untitled session"


@dataclass(frozen=True)
class SessionSummary:
    """One row of the session list. Everything a door needs to draw it, and nothing else."""

    id: str
    title: str
    step: str
    updated: float  # epoch seconds, so the door decides how to phrase it


class SessionStore:
    """A directory of session directories."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ── finding ────────────────────────────────────────────────────────────

    def _files(self) -> list[Path]:
        """Every session file under the root.

        Two shapes are accepted because two doors write them: `<root>/<id>/session.json`,
        which is what this door creates and what `--out-dir` resumes, and `<root>/session.json`,
        which is what the CLI writes when pointed straight at the root.
        """
        found = []
        direct = self.root / SESSION_FILENAME
        if direct.is_file():
            found.append(direct)
        found.extend(sorted(self.root.glob(f"*/{SESSION_FILENAME}")))
        return found

    def list(self) -> list[SessionSummary]:
        """Newest first. A file that cannot be read is left out rather than fatal.

        An older session written before the format changed would otherwise take the whole
        list down with it, which is a bad trade: one unreadable session should cost you that
        session, not every other one.
        """
        summaries = []
        for path in self._files():
            summary = self._summarise(path)
            if summary is not None:
                summaries.append(summary)
        return sorted(summaries, key=lambda s: s.updated, reverse=True)

    def _summarise(self, path: Path) -> SessionSummary | None:
        try:
            raw = json.loads(path.read_text())
            session_id = raw["id"]
            step = raw["step"]
            name = (raw.get("profile", {}).get("product", {}).get("name") or "").strip()
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            return None

        return SessionSummary(
            id=session_id,
            title=name or UNTITLED,
            step=step,
            updated=path.stat().st_mtime,
        )

    def path_for(self, session_id: str) -> Path | None:
        """The file holding this session, or None if no directory carries it.

        Resolved by reading rather than by assuming the directory is named after the id, so
        a session the CLI wrote into a directory the user named still resolves.
        """
        for path in self._files():
            try:
                if json.loads(path.read_text()).get("id") == session_id:
                    return path
            except (OSError, ValueError):
                continue
        return None

    # ── creating and loading ───────────────────────────────────────────────

    def new_path(self, session_id: str) -> Path:
        """Where a session with this id should be written."""
        return self.root / session_id / SESSION_FILENAME

    def load(self, session_id: str) -> SessionState | None:
        path = self.path_for(session_id)
        return SessionState.load(path) if path is not None else None
