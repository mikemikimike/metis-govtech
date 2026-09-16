"""Library artifact extraction reads the unified core.Artifact shape (#307)."""

from __future__ import annotations

from pathlib import Path

from deepeval.test_case import LLMTestCase

from metis.core import Artifact
from metis.library.metrics._extraction import _artifact_paths, get_artifacts


def _case(artifacts: list[dict]) -> LLMTestCase:
    return LLMTestCase(input="i", actual_output="o", metadata={"artifacts": artifacts})


def test_get_artifacts_validates_to_core_artifact() -> None:
    tc = _case([{"name": "out.csv", "uri": "file:///tmp/out.csv"}])
    arts = get_artifacts(tc)
    assert len(arts) == 1
    assert isinstance(arts[0], Artifact)
    assert arts[0].name == "out.csv"
    assert arts[0].uri == "file:///tmp/out.csv"


def test_get_artifacts_skips_malformed_dicts() -> None:
    # missing required 'name'/'type' → skipped, not raised
    tc = _case([{"uri": "file:///tmp/x"}, {"name": "ok.csv"}])
    arts = get_artifacts(tc)
    assert [a.name for a in arts] == ["ok.csv"]


def test_get_artifacts_empty_when_absent() -> None:
    assert get_artifacts(LLMTestCase(input="i", actual_output="o")) == []


def test_artifact_paths_resolve_from_uri(tmp_path: Path) -> None:
    deck = tmp_path / "slides.pptx"
    deck.write_bytes(b"PK\x03\x04")
    tc = _case([{"name": "slides.pptx", "uri": deck.as_uri()}])
    assert _artifact_paths(tc, ".pptx") == [str(deck)]
    assert _artifact_paths(tc, ".csv") == []


def test_artifact_paths_skips_non_file_uri() -> None:
    tc = _case([{"name": "remote.csv", "uri": "s3://b/remote.csv"}])
    assert _artifact_paths(tc, ".csv") == []
