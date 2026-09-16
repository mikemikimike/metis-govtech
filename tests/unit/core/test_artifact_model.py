"""Unified Artifact model + uri_to_local_path helper (#307)."""

from __future__ import annotations

from pathlib import Path

from metis.core import Artifact, uri_to_local_path


def test_artifact_auto_id_is_unique() -> None:
    a, b = (
        Artifact(name="x.csv"),
        Artifact(name="x.csv"),
    )
    assert a.id and b.id and a.id != b.id


def test_artifact_enrichment_fields_default_none() -> None:
    a = Artifact(name="x.csv")
    assert a.uri is None
    assert a.at_turn is None
    assert a.content_description is None
    assert a.state_description is None
    assert a.digest is None
    assert a.hash_algorithm is None


def test_artifact_round_trips() -> None:
    a = Artifact(
        name="report.csv",
        uri="file:///tmp/report.csv",
        at_turn=3,
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


def test_source_defaults_to_target() -> None:
    assert Artifact(name="report.pdf").source == "target"


def test_source_can_be_fixture() -> None:
    assert Artifact(name="input.csv", source="fixture").source == "fixture"


def test_media_type_derived_from_name() -> None:
    assert Artifact(name="report.pdf").media_type == "application/pdf"
    assert Artifact(name="chart.png").media_type == "image/png"
    assert (
        Artifact(name="deck.pptx").media_type
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


def test_media_type_none_when_extensionless() -> None:
    assert Artifact(name="noext").media_type is None


def test_media_type_falls_back_to_uri() -> None:
    a = Artifact(name="noext", uri="file:///tmp/report.pdf")
    assert a.media_type == "application/pdf"


def test_media_type_serialised_into_dump() -> None:
    dumped = Artifact(name="report.pdf", source="fixture").model_dump()
    assert dumped["source"] == "fixture"
    assert dumped["media_type"] == "application/pdf"
    assert "type" not in dumped
