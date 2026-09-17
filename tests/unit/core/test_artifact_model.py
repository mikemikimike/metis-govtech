"""The Artifact domain model and resolve_artifact_path (#328)."""

from __future__ import annotations

from pathlib import Path

from metis.core import Artifact, resolve_artifact_path


def test_artifact_defaults() -> None:
    art = Artifact(name="report.csv")
    assert art.source == "target"
    assert art.path is None
    assert art.at_turn is None
    assert art.content_description is None
    assert art.state_description is None
    assert art.digest is None
    assert art.hash_algorithm is None
    assert art.id  # auto-generated


def test_artifact_round_trips() -> None:
    art = Artifact(
        name="report.csv",
        source="target",
        path="runs/s1-p1-1/artifacts/report.csv",
        at_turn=2,
        content_description="Q3 sales export",
        digest="a" * 64,
        hash_algorithm="SHA256",
    )
    restored = Artifact.model_validate(art.model_dump())
    assert restored == art


def test_media_type_guessed_from_name() -> None:
    art = Artifact(name="report.csv")
    assert art.media_type == "text/csv"


def test_media_type_falls_back_to_path() -> None:
    art = Artifact(name="report", path="runs/x/artifacts/report.csv")
    assert art.media_type == "text/csv"


def test_media_type_none_when_unresolvable() -> None:
    art = Artifact(name="report")
    assert art.media_type is None


def test_resolve_artifact_path_joins_relative_path(tmp_path: Path) -> None:
    resolved = resolve_artifact_path(tmp_path, "runs/s1-p1-1/artifacts/report.csv")
    assert resolved == tmp_path / "runs/s1-p1-1/artifacts/report.csv"


def test_resolve_artifact_path_none_when_path_falsy(tmp_path: Path) -> None:
    assert resolve_artifact_path(tmp_path, None) is None
    assert resolve_artifact_path(tmp_path, "") is None
