"""Unified Artifact model + uri_to_local_path helper (#307)."""

from __future__ import annotations

from pathlib import Path

from metis.core import Artifact, uri_to_local_path


def test_artifact_auto_id_is_unique() -> None:
    a, b = (
        Artifact(name="x.csv", type="download"),
        Artifact(name="x.csv", type="download"),
    )
    assert a.id and b.id and a.id != b.id


def test_artifact_enrichment_fields_default_none() -> None:
    a = Artifact(name="x.csv", type="download")
    assert a.uri is None
    assert a.collected_at_turn is None
    assert a.content_description is None
    assert a.state_description is None
    assert a.digest is None
    assert a.hash_algorithm is None


def test_artifact_round_trips() -> None:
    a = Artifact(
        name="report.csv",
        type="download",
        uri="file:///tmp/report.csv",
        collected_at_turn=3,
        content_description="120 rows x 4 cols; total sales 9,999",
        state_description="delivered at turn 3",
        digest="deadbeef",
        hash_algorithm="SHA256",
    )
    assert Artifact.model_validate(a.model_dump()) == a


def test_uri_to_local_path_resolves_file_uri(tmp_path: Path) -> None:
    f = tmp_path / "a.csv"
    f.write_text("x")
    assert uri_to_local_path(f.as_uri()) == f


def test_uri_to_local_path_skips_other_schemes() -> None:
    assert uri_to_local_path(None) is None
    assert uri_to_local_path("s3://bucket/key") is None
    assert uri_to_local_path("https://example.com/x.csv") is None
    assert uri_to_local_path("blob:https://app/abc") is None
