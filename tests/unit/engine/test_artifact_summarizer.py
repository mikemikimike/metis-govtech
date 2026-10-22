"""Artifact summarizer: digest, fact-rich text, graceful degrade, never raises (#307, #328)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from metis.core import Artifact
from metis.engine.simulation.gen_1 import artifact_summarizer as summ
from metis.engine.simulation.gen_1.artifact_summarizer import (
    _SUMMARIZER_SYSTEM,
    summarize_artifact,
)
from metis.engine.simulation.llm_calls import LLMCallLog


@pytest.mark.asyncio
async def test_digest_is_sha256_of_bytes(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "data.csv"
    payload = b"a,b\n1,2\n"
    f.write_bytes(payload)

    async def _fake(text, *, name, triggering_message, turn_number, llm_log):
        return ("2 rows x 2 cols", f"delivered at turn {turn_number}")

    monkeypatch.setattr(summ, "_summarize_via_llm", _fake)
    art = Artifact(name="data.csv", path="data.csv", state="received")
    await summarize_artifact(
        art,
        experiment_root=tmp_path,
        triggering_message="make a csv",
        turn_number=3,
        llm_log=LLMCallLog.for_trial(tmp_path),
    )

    assert art.digest == hashlib.sha256(payload).hexdigest()
    assert art.hash_algorithm == "SHA256"


@pytest.mark.asyncio
async def test_fact_rich_description_from_stubbed_llm(
    tmp_path: Path, monkeypatch
) -> None:
    f = tmp_path / "sales.csv"
    f.write_text("region,total\nnorth,100\nsouth,200\n")

    async def _fake(text, *, name, triggering_message, turn_number, llm_log):
        assert "region,total" in text  # the file content reaches the LLM
        return ("2 data rows; totals north=100 south=200", "delivered at turn 2")

    monkeypatch.setattr(summ, "_summarize_via_llm", _fake)
    art = Artifact(name="sales.csv", path="sales.csv", state="received")
    await summarize_artifact(
        art,
        experiment_root=tmp_path,
        triggering_message="totals please",
        turn_number=2,
        llm_log=LLMCallLog.for_trial(tmp_path),
    )

    assert "north=100" in (art.content_description or "")
    assert art.state_description == "delivered at turn 2"


@pytest.mark.asyncio
async def test_binary_degrades_without_llm(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "deck.pptx"
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 32)

    async def _boom(*a, **k):
        raise AssertionError("LLM must not be called for binary files")

    monkeypatch.setattr(summ, "_summarize_via_llm", _boom)
    art = Artifact(name="deck.pptx", path="deck.pptx", state="received")
    await summarize_artifact(
        art,
        experiment_root=tmp_path,
        triggering_message="make slides",
        turn_number=1,
        llm_log=LLMCallLog.for_trial(tmp_path),
    )

    assert art.digest is not None
    assert "not text-summarized" in (art.content_description or "")


@pytest.mark.asyncio
async def test_llm_failure_never_raises(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello")

    async def _fail(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(summ, "_summarize_via_llm", _fail)
    art = Artifact(name="notes.txt", path="notes.txt", state="received")
    await summarize_artifact(
        art,
        experiment_root=tmp_path,
        triggering_message="save notes",
        turn_number=1,
        llm_log=LLMCallLog.for_trial(tmp_path),
    )  # no raise

    assert art.digest is not None
    assert art.content_description  # a fallback string was set


@pytest.mark.asyncio
async def test_missing_file_is_noop(tmp_path: Path) -> None:
    art = Artifact(name="gone.csv", path="nope/gone.csv", state="received")
    await summarize_artifact(
        art,
        experiment_root=tmp_path,
        triggering_message="x",
        turn_number=1,
        llm_log=LLMCallLog.for_trial(tmp_path),
    )  # no raise
    assert art.digest is None
    assert art.content_description is None


@pytest.mark.asyncio
async def test_state_gate_is_checked_before_touching_disk(tmp_path: Path) -> None:
    """The new early-return fires on state alone, even for a file that
    genuinely exists on disk — proving it's a real gate, not a restatement
    of the is_file() check test_missing_file_is_noop already covers."""
    real_file = tmp_path / "notes.txt"
    real_file.write_text("hello")
    artifact = Artifact(
        name="notes.txt", path="notes.txt", state="unfetched", external_id="f-1"
    )
    await summarize_artifact(
        artifact,
        experiment_root=tmp_path,
        triggering_message="here you go",
        turn_number=1,
        llm_log=LLMCallLog.for_trial(tmp_path),
    )
    assert artifact.content_description is None
    assert artifact.digest is None


@pytest.mark.asyncio
async def test_summarize_fixtures_skips_described_and_fills_gaps(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "notes.txt").write_text("hello world")
    described = Artifact(
        name="q3.csv",
        source="fixture",
        path="notes.txt",
        state="received",
        content_description="author supplied",
    )
    gap = Artifact(
        name="notes.txt",
        source="fixture",
        path="notes.txt",
        state="received",
    )

    calls: list[str] = []

    async def fake_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log
    ):
        calls.append(artifact.name)
        artifact.content_description = "auto"
        artifact.state_description = f"delivered at turn {turn_number}"

    monkeypatch.setattr(
        "metis.engine.simulation.gen_1.artifact_summarizer.summarize_artifact",
        fake_summarize,
    )

    from metis.engine.simulation.gen_1.artifact_summarizer import (
        summarize_fixture_artifacts,
    )

    await summarize_fixture_artifacts(
        [described, gap], tmp_path, llm_log=LLMCallLog.for_trial(tmp_path)
    )

    assert calls == ["notes.txt"]  # described one skipped
    assert described.content_description == "author supplied"
    assert gap.content_description == "auto"
    assert gap.state_description is None  # cleared for fixtures


@pytest.mark.asyncio
async def test_resolve_fixture_descriptions_summarizes_each_unique_once(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "shared.csv").write_text("a,b\n1,2\n")
    (tmp_path / "author.csv").write_text("x,y\n3,4\n")

    calls: list[str] = []

    async def fake_summarize(
        artifact, *, experiment_root, triggering_message, turn_number, llm_log
    ):
        calls.append(artifact.name)
        artifact.content_description = f"auto:{artifact.name}"
        artifact.state_description = f"delivered at turn {turn_number}"

    monkeypatch.setattr(
        "metis.engine.simulation.gen_1.artifact_summarizer.summarize_artifact",
        fake_summarize,
    )

    from metis.engine.simulation.gen_1.artifact_summarizer import (
        resolve_fixture_descriptions,
    )

    # "shared.csv" appears in two scenarios; "author.csv" is described in yaml.
    resolved = await resolve_fixture_descriptions(
        ["shared.csv", "author.csv", "shared.csv"],
        tmp_path,
        tmp_path,
        {"author.csv": "author supplied"},
    )

    # Each unique undescribed fixture is summarized exactly once, despite the
    # duplicate; the author-described one is never summarized.
    assert calls == ["shared.csv"]
    assert resolved == {
        "shared.csv": "auto:shared.csv",
        "author.csv": "author supplied",
    }


@pytest.mark.asyncio
async def test_resolve_fixture_descriptions_omits_missing_files(
    tmp_path: Path, monkeypatch
) -> None:
    async def _boom(*a, **k):
        raise AssertionError("no summarization for a missing file")

    monkeypatch.setattr(
        "metis.engine.simulation.gen_1.artifact_summarizer.summarize_artifact",
        _boom,
    )

    from metis.engine.simulation.gen_1.artifact_summarizer import (
        resolve_fixture_descriptions,
    )

    # File never staged on disk -> build_fixture_artifacts skips it -> absent
    # from the map (workers likewise skip it, so the two stay consistent).
    resolved = await resolve_fixture_descriptions(["ghost.csv"], tmp_path, tmp_path, {})
    assert resolved == {}


class TestSummarizerScope:
    def test_prompt_forbids_restating_other_files(self) -> None:
        """A document's own manifest of siblings must not become METIS's claim."""
        prompt = _SUMMARIZER_SYSTEM.lower()
        assert "only what is in this one file" in prompt
        assert "other file" in prompt or "sibling" in prompt
        assert "claims" in prompt

    def test_prompt_still_demands_specific_figures(self) -> None:
        """Over-restricting loses the detail the persona judges sufficiency from."""
        prompt = _SUMMARIZER_SYSTEM.lower()
        assert "fact-rich" in prompt
        assert "row and column counts" in prompt
        assert "be specific with numbers" in prompt
