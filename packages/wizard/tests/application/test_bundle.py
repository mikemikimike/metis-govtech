from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml
from fixtures.profiles import research_assistant

from metis.wizard.application.compile import BundleError, write_bundle
from metis.wizard.contracts import ProductProfile


def _document(*fixtures: str) -> dict:
    return {
        "schema_version": 1,
        "id": "bundle-test",
        "description": "A bundle test.",
        "personas": [{"id": "p", "description": "A person."}],
        "scenarios": [
            {
                "id": "S-1",
                "description": "Use the fixtures.",
                "num_trials": 1,
                "persona_refs": ["p"],
                "metric_refs": [],
                **({"fixtures": list(fixtures)} if fixtures else {}),
            }
        ],
    }


def test_bundle_has_engine_input_shape_and_opaque_bytes(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "policy.html").write_bytes(b"<script>alert(1)</script>")
    (fixture_dir / "data.csv").write_text("a,b\n1,2\n")
    target = tmp_path / "experiment.zip"

    write_bundle(_document("policy.html"), fixture_dir, target)

    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == [
            "experiment.yaml",
            "fixtures/",
            "fixtures/data.csv",
            "fixtures/policy.html",
        ]
        assert archive.read("fixtures/policy.html") == b"<script>alert(1)</script>"
        assert "tasks:" not in archive.read("experiment.yaml").decode()


def test_bundle_keeps_an_explicit_empty_fixtures_directory(tmp_path: Path) -> None:
    target = tmp_path / "experiment.zip"
    write_bundle(_document(), tmp_path / "fixtures", target)

    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ["experiment.yaml", "fixtures/"]


def test_bundle_can_include_a_portable_profile(tmp_path: Path) -> None:
    profile = research_assistant()
    target = tmp_path / "experiment.zip"

    write_bundle(
        _document(),
        tmp_path / "fixtures",
        target,
        profile=profile,
    )

    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == [
            "experiment.yaml",
            "profile.yaml",
            "fixtures/",
        ]
        saved = ProductProfile.model_validate(
            yaml.safe_load(archive.read("profile.yaml"))
        )

    assert saved == profile


def test_bundle_refuses_missing_referenced_file(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()

    with pytest.raises(BundleError, match="missing.txt"):
        write_bundle(_document("missing.txt"), fixture_dir, tmp_path / "experiment.zip")
