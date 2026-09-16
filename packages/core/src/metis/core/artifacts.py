"""The ``Artifact`` domain model and its URI resolver.

An Artifact is the single model for a file crossing the persona<->target
boundary in a simulation: live-detected in the UI, downloaded to disk, then
enriched with descriptions and a digest. It lives in ``core`` so every package
shares one definition without violating the dependency DAG — the engine
produces them, the library reads them, and the wizard may synthesize them,
none of which may import the engine.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from urllib.request import url2pathname
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


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
    uri: str | None = None  # file:// for local; s3://, nas:// reserved
    at_turn: int | None = None
    content_description: str | None = None  # summarizer-filled; must be fact-rich
    state_description: str | None = None  # e.g. "delivered at turn 3 after ..."
    digest: str | None = None  # e.g. hex SHA-256 of the bytes
    hash_algorithm: str | None = None  # e.g. "SHA256"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def media_type(self) -> str | None:
        """MIME type inferred from ``name`` (then ``uri``); ``None`` if unknown.

        Single source of truth is the filename, so the format never drifts on
        rename. Keys off the extension via stdlib ``mimetypes``, so an
        extensionless locator yields ``None``.
        """
        guessed, _ = mimetypes.guess_type(self.name)
        if guessed is None and self.uri:
            guessed, _ = mimetypes.guess_type(self.uri)
        return guessed


def uri_to_local_path(uri: str | None) -> Path | None:
    """Return a local ``Path`` for a ``file://`` URI, else ``None``.

    ``file://`` URIs (produced by the runners for on-disk downloads) resolve
    to a ``Path``; every other scheme (``s3://``, ``nas://``, ``blob:``,
    ``http(s)``) returns ``None`` because it is not locally resolvable yet.
    """
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(url2pathname(parsed.path))
