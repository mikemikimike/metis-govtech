"""The ``Artifact`` domain model and its URI resolver.

An Artifact is the single model for a file crossing the persona<->target
boundary in a simulation: live-detected in the UI, downloaded to disk, then
enriched with descriptions and a digest. It lives in ``core`` so every package
shares one definition without violating the dependency DAG — the engine
produces them, the library reads them, and the wizard may synthesize them,
none of which may import the engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from urllib.request import url2pathname
from uuid import uuid4

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    """A downloadable/renderable item produced by the target.

    One model across the lifecycle: live-detected in the UI, downloaded to
    disk, then enriched with descriptions and a digest by the summarizer.
    Enrichment fields stay None for items never downloaded (``preview``/
    ``chart``) or that could not be downloaded/summarized.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    type: Literal["download", "preview", "chart"]
    uri: str | None = None  # file:// for local; s3://, nas:// reserved
    collected_at_turn: int | None = None
    content_description: str | None = None  # summarizer-filled; must be fact-rich
    state_description: str | None = None  # e.g. "delivered at turn 3 after ..."
    digest: str | None = None  # e.g. hex SHA-256 of the bytes
    hash_algorithm: str | None = None  # e.g. "SHA256"


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
