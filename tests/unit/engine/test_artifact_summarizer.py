"""Artifact summarizer: digest, fact-rich text, graceful degrade, never raises (#307)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from metis.core import Artifact
from metis.engine.simulation import artifact_summarizer as summ
from metis.engine.simulation.artifact_summarizer import summarize_artifact


@pytest.mark.asyncio
async def test_digest_is_sha256_of_bytes(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "data.csv"
    payload = b"a,b\n1,2\n"
    f.write_bytes(payload)

    async def _fake(text, *, name, triggering_message, turn_number):
        return ("2 rows x 2 cols", f"delivered at turn {turn_number}")

    monkeypatch.setattr(summ, "_summarize_via_llm", _fake)
    art = Artifact(name="data.csv", type="download", uri=f.as_uri())
    await summarize_artifact(art, triggering_message="make a csv", turn_number=3)

    assert art.digest == hashlib.sha256(payload).hexdigest()
    assert art.hash_algorithm == "SHA256"


@pytest.mark.asyncio
async def test_fact_rich_description_from_stubbed_llm(
    tmp_path: Path, monkeypatch
) -> None:
    f = tmp_path / "sales.csv"
    f.write_text("region,total\nnorth,100\nsouth,200\n")

    async def _fake(text, *, name, triggering_message, turn_number):
        assert "region,total" in text  # the file content reaches the LLM
        return ("2 data rows; totals north=100 south=200", "delivered at turn 2")

    monkeypatch.setattr(summ, "_summarize_via_llm", _fake)
    art = Artifact(name="sales.csv", type="download", uri=f.as_uri())
    await summarize_artifact(art, triggering_message="totals please", turn_number=2)

    assert "north=100" in (art.content_description or "")
    assert art.state_description == "delivered at turn 2"


@pytest.mark.asyncio
async def test_binary_degrades_without_llm(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "deck.pptx"
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 32)

    async def _boom(*a, **k):
        raise AssertionError("LLM must not be called for binary files")

    monkeypatch.setattr(summ, "_summarize_via_llm", _boom)
    art = Artifact(name="deck.pptx", type="download", uri=f.as_uri())
    await summarize_artifact(art, triggering_message="make slides", turn_number=1)

    assert art.digest is not None
    assert "not text-summarized" in (art.content_description or "")


@pytest.mark.asyncio
async def test_llm_failure_never_raises(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello")

    async def _fail(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(summ, "_summarize_via_llm", _fail)
    art = Artifact(name="notes.txt", type="download", uri=f.as_uri())
    await summarize_artifact(
        art, triggering_message="save notes", turn_number=1
    )  # no raise

    assert art.digest is not None
    assert art.content_description  # a fallback string was set


@pytest.mark.asyncio
async def test_missing_file_is_noop(monkeypatch) -> None:
    art = Artifact(name="gone.csv", type="download", uri="file:///nope/gone.csv")
    await summarize_artifact(art, triggering_message="x", turn_number=1)  # no raise
    assert art.digest is None
    assert art.content_description is None
