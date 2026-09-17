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
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    source: Literal["fixture", "target"] = "target"
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
