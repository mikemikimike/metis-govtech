"""The ``Artifact`` domain model and its path resolver.

An ``Artifact`` records a file produced or consumed during a simulation run
(a fixture supplied to the target, or a document/image the target produced).
Its ``path`` is a POSIX-style path relative to the experiment root — the
directory created by ``metis engine simulate`` (or resumed into), containing
``inputs/`` and ``runs/``. Storing a relative path keeps experiment output
directories portable: they can be copied, zipped, or moved without breaking
artifact references baked into ``record.json``.
"""

from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from pathlib import Path


class Artifact(BaseModel):
    """A file crossing the persona<->target boundary.

    One model across the lifecycle and both directions: an inbound fixture
    (``source="fixture"``) or an outbound target output (``source="target"``),
    optionally downloaded to disk and enriched with descriptions and a digest.
    Enrichment fields stay ``None`` until the bytes are in hand and summarized.

    ``id`` identifies this record; ``external_id`` identifies the *file* on the
    target's side, which is what makes a completed run re-checkable against the
    target and what lets a collector dedupe by identity rather than filename.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    source: Literal["fixture", "target"] = "target"
    #: The target system's own identifier for this file (Orca's ``fileId``).
    #: Target-agnostic by name because ``metis-core`` must not know about Orca.
    #: ``None`` for runners with no such identifier, such as the browser runner.
    #:
    #: **Must name exactly one file within its ``source``, or leave it**
    #: ``None``. Consumers treat two records that share a ``source`` and a
    #: non-``None`` ``external_id`` as one file and keep only one of them, so an
    #: id a target reuses across genuinely different files makes those files
    #: collapse into a single record: they vanish from the run, and from the list
    #: the simulated user is told is every file it received. Nothing enforces
    #: this — uniqueness is a property of the set, not of any one record a
    #: validator can see — so it is a promise each runner makes. A runner that
    #: cannot make it must leave this ``None``, which is always safe: an absent
    #: id costs deduplication, never a file. Reusing one id across a target's
    #: *revisions* of a file is equally a violation; a revision is a different
    #: file and needs its own id, or the run cannot show that anything changed.
    external_id: str | None = None
    path: str | None = None
    at_turn: int | None = None
    content_description: str | None = None
    state_description: str | None = None
    digest: str | None = None
    hash_algorithm: str | None = None

    @computed_field
    @property
    def media_type(self) -> str | None:
        """Best-effort MIME type guessed from the filename (or path as fallback)."""
        guessed, _ = mimetypes.guess_type(self.name)
        if guessed is None and self.path:
            guessed, _ = mimetypes.guess_type(self.path)
        return guessed


def resolve_artifact_path(experiment_root: Path, path: str | None) -> Path | None:
    """Resolve an ``Artifact.path`` against the experiment root.

    Returns ``None`` when ``path`` is falsy (no file was recorded for this
    artifact).
    """
    if not path:
        return None
    return experiment_root / path
