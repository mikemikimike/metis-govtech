"""Where interviews live, and how the door finds them.

There is no database and no index. An interview is an `interview_state.json` inside its own
directory, which is exactly what `metis wizard init --out-dir <dir>` already writes — so an
interview started in the browser is resumable from the terminal by pointing `--out-dir` at its
directory, and one started in the terminal shows up in the browser list. Two doors, one
directory, nothing to keep in step.

Listing reads each file, which is fine at the scale a local wizard runs at and avoids the
one thing an index would add: a second record of the truth that can go stale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from metis.wizard.contracts.interview_state import InterviewState

INTERVIEW_STATE_FILENAME = "interview_state.json"
UNTITLED = "Untitled interview"


@dataclass(frozen=True)
class InterviewSummary:
    """One row of the interview list. Everything a door needs to draw it, and nothing else."""

    id: str
    title: str
    step: str
    updated: float  # epoch seconds, so the door decides how to phrase it


class InterviewStore:
    """A directory of interview directories."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _files(self) -> list[Path]:
        """Every interview file under the root.

        Two shapes are accepted because two doors write them:
        `<root>/<id>/interview_state.json`, which is what this door creates and what
        `--out-dir` resumes, and `<root>/interview_state.json`, which is what the CLI writes
        when pointed straight at the root.
        """
        found = []
        direct = self.root / INTERVIEW_STATE_FILENAME
        if direct.is_file():
            found.append(direct)
        found.extend(sorted(self.root.glob(f"*/{INTERVIEW_STATE_FILENAME}")))
        return found

    def list(self) -> list[InterviewSummary]:
        """Newest first. A file that cannot be read is left out rather than fatal.

        An older interview written before the format changed would otherwise take the whole
        list down with it, which is a bad trade: one unreadable interview should cost you that
        interview, not every other one.
        """
        summaries = []
        for path in self._files():
            summary = self._summarise(path)
            if summary is not None:
                summaries.append(summary)
        return sorted(summaries, key=lambda s: s.updated, reverse=True)

    def _summarise(self, path: Path) -> InterviewSummary | None:
        try:
            raw = json.loads(path.read_text())
            interview_id = raw["id"]
            step = raw["step"]
            name = (raw.get("profile", {}).get("product", {}).get("name") or "").strip()
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            return None

        return InterviewSummary(
            id=interview_id,
            title=name or UNTITLED,
            step=step,
            updated=path.stat().st_mtime,
        )

    def path_for(self, interview_id: str) -> Path | None:
        """The file holding this interview, or None if no directory carries it.

        Resolved by reading rather than by assuming the directory is named after the id, so
        an interview the CLI wrote into a directory the user named still resolves.
        """
        for path in self._files():
            try:
                if json.loads(path.read_text()).get("id") == interview_id:
                    return path
            except (OSError, ValueError):
                continue
        return None

    def new_path(self, interview_id: str) -> Path:
        """Where an interview with this id should be written."""
        return self.root / interview_id / INTERVIEW_STATE_FILENAME

    def load(self, interview_id: str) -> InterviewState | None:
        path = self.path_for(interview_id)
        return InterviewState.load(path) if path is not None else None
