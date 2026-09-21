"""Tests for the runner-agnostic artifact store."""

from __future__ import annotations

import json
from pathlib import Path

from metis.core import Artifact
from metis.engine.simulation._artifact_store import _save_artifacts, infer_artifact_type
from metis.engine.simulation.types import (
    RunConfig,
    RunOutcome,
    RunRecord,
)


class TestInferArtifactType:
    def test_pdf_is_report(self) -> None:
        assert infer_artifact_type("output.pdf") == "report"

    def test_png_is_chart(self) -> None:
        assert infer_artifact_type("graph.png") == "chart"

    def test_csv_is_data(self) -> None:
        assert infer_artifact_type("results.csv") == "data"

    def test_unknown_extension(self) -> None:
        assert infer_artifact_type("file.xyz") == "unknown"

    def test_no_extension(self) -> None:
        assert infer_artifact_type("noext") == "unknown"


class TestSaveArtifacts:
    def test_writes_manifest(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "s1-p1-1"
        run_dir.mkdir(parents=True)
        record = RunRecord(
            config=RunConfig(persona="p1", scenario="s1", metric_refs=[]),
            target_session_id="sess-abc",
            outcome=RunOutcome(
                stop_reason="goal_achieved", total_turns=3, duration_seconds=10.0
            ),
            conversation=[],
            artifacts=[
                Artifact(
                    name="report.pdf",
                    path="runs/s1-p1-1/artifacts/report.pdf",
                    at_turn=2,
                ),
                Artifact(
                    name="input.csv",
                    source="fixture",
                    path="inputs/fixtures/input.csv",
                ),
            ],
        )
        manifest = _save_artifacts(record, run_dir, tmp_path)
        assert manifest["session_id"] == "sess-abc"
        assert len(manifest["artifacts"]) == 2
        assert manifest["artifacts"][0]["type"] == "report"

        manifest_path = run_dir / "artifacts" / "run-manifest.json"
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text())
        assert saved == manifest

        by_name = {a["filename"]: a for a in manifest["artifacts"]}
        assert by_name["report.pdf"]["source"] == "target"
        assert by_name["report.pdf"]["path"] == str(
            tmp_path / "runs/s1-p1-1/artifacts/report.pdf"
        )
        assert by_name["input.csv"]["source"] == "fixture"


def test_manifest_keeps_logical_name_when_disk_path_is_decollided(tmp_path):
    # A target file whose on-disk name was de-collided (report.txt -> report-2.txt)
    # while the logical announced name stayed "report.txt".
    disk = tmp_path / "report-2.txt"
    disk.write_text("x")
    art = Artifact(name="report.txt", source="target", path="report-2.txt")
    record = RunRecord(
        config=RunConfig(persona="p", scenario="s"),
        outcome=RunOutcome(
            stop_reason="goal_achieved", total_turns=1, duration_seconds=1.0
        ),
        artifacts=[art],
    )

    manifest = _save_artifacts(record, tmp_path, tmp_path)
    entry = manifest["artifacts"][0]

    assert entry["filename"] == "report.txt"  # logical label, never mutated
    assert entry["path"].endswith("report-2.txt")  # on-disk truth from path
    assert entry["filename"] != Path(entry["path"]).name  # allowed to diverge


def test_manifest_carries_external_id(tmp_path: Path) -> None:
    """Built field-by-field, so the new field needs a deliberate line."""
    record = RunRecord(
        config=RunConfig(persona="p", scenario="s"),
        outcome=RunOutcome(
            stop_reason="goal_achieved", total_turns=1, duration_seconds=1.0
        ),
        artifacts=[
            Artifact(name="chart.vl.json", external_id="73da06dac970f8a9", path=None),
            Artifact(name="local.png", path=None),
        ],
    )
    manifest = _save_artifacts(record, tmp_path / "run", tmp_path)
    assert [a["external_id"] for a in manifest["artifacts"]] == [
        "73da06dac970f8a9",
        None,
    ]
