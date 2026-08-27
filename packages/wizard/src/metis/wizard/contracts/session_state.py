"""Everything that survives a restart — one JSON file.

`SessionState` is data. `Session` (next door) is the object with `.next()` and `.respond()`.
Only the first is persisted, and that split is what lets a CLI and an HTTP server both
rehydrate mid-conversation: a web door cannot hold a conversation in a process variable
between requests, so it loads the state, applies one response, and saves it again.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import BaseModel, Field

from metis.wizard.contracts.conversation import AnyRequest, WizardRequestState
from metis.wizard.domain.permissions import SessionStep

if TYPE_CHECKING:
    from metis.wizard.domain.profile import ProductProfile

SESSION_FORMAT_VERSION = 5


class SessionVersionError(Exception):
    """A session file written by a different version of the wizard."""


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class SessionState(BaseModel):
    """One JSON file. Rewritten after every response, atomically."""

    version: int = SESSION_FORMAT_VERSION
    id: str
    profile: ProductProfile
    # `step` lives here, not on ProductProfile. The profile describes the product; where the
    # interview got to is conversation state. Keeping them apart is what makes the profile a
    # pure artefact — renderable, compilable and hand-writable without inventing a step.
    step: SessionStep = SessionStep.CLARIFY
    history: list[Turn] = Field(default_factory=list)
    # Every screen this session has composed, in order. The last is the one being looked at;
    # everything before it has been answered. A terminal only ever needed the last one, which
    # is why this was a single slot until a door had to keep the conversation on screen.
    #
    # `history` is not the same record and does not replace this one. It is prose, and it is
    # what the model is shown; this is structure, and it is what a door redraws.
    requests: list[AnyRequest] = Field(default_factory=list)

    # ── the live screen ────────────────────────────────────────────────────

    # `pending` is a property rather than a field, and that is load-bearing rather than
    # tidy: every existing caller assigns and reads it, so keeping the name keeps the
    # driver, the CLI door and their tests untouched. Being a property also means it is not
    # serialised — the list is the single persisted representation, so the two cannot drift.

    @property
    def pending(self) -> AnyRequest | None:
        last = self.requests[-1] if self.requests else None
        if last is not None and last.state is WizardRequestState.PENDING:
            return last
        return None

    @pending.setter
    def pending(self, request: AnyRequest | None) -> None:
        if request is None:
            self.resolve_pending()
        elif self.pending is not None:
            # The same screen, recomposed. Replacing rather than appending is what stops a
            # tick from stacking a second copy of the screen it was ticked on.
            self.requests[-1] = request
        else:
            self.requests.append(request)

    def resolve_pending(self) -> None:
        """Mark the live screen answered. A no-op when nothing is live."""
        if self.pending is not None:
            self.requests[-1].state = WizardRequestState.RESOLVED

    # ── persistence ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> Self:
        """Load a session, checking the format version before anything else parses.

        These models change daily during development and `resume` was promised to be safe.
        A mismatch is refused by name — not surfaced as a validation error about a field
        nobody has heard of. There are deliberately no migration functions while the models
        are still moving; the message tells you to start a new session, and that is the
        whole policy.
        """
        path = Path(path)
        raw: Any = json.loads(path.read_text())

        version = raw.get("version") if isinstance(raw, dict) else None
        if version != SESSION_FORMAT_VERSION:
            raise SessionVersionError(
                f"This session was written by a different wizard "
                f"(format {version}, this is {SESSION_FORMAT_VERSION}) "
                f"and can't be resumed: {path}. Start a new session."
            )

        return cls.model_validate(raw)

    def save(self, path: Path) -> None:
        """Write atomically: a temp file in the same directory, then `os.replace`.

        A crash mid-write leaves the previous good session rather than a truncated file,
        which is the difference between losing one turn and losing the interview.

        This guards the *file*, not the *document*: a patch set that failed halfway would be
        saved perfectly atomically in a state that was never meant to exist. That case is
        removed a level up instead — anything the user can click together is guaranteed not
        to conflict. See `multi`.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.model_dump(mode="json"), indent=2) + "\n"

        # Same directory, so the replace is a rename within one filesystem.
        handle, temp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, path)
        except BaseException:
            # Leave no debris behind on the way out — a stray temp file next to a session
            # is indistinguishable from a half-written one to anybody reading the directory.
            Path(temp_name).unlink(missing_ok=True)
            raise
