"""Tests for the runner-agnostic artifact store."""

from __future__ import annotations

import json
from pathlib import Path

from metis.engine.simulation._artifact_store import _save_artifacts, infer_artifact_type
from metis.engine.simulation.types import (
    CollectedArtifact,
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
        record = RunRecord(
            config=RunConfig(persona="p1", scenario="s1", metric_refs=[]),
            target_session_id="sess-abc",
            outcome=RunOutcome(
                stop_reason="goal_achieved", total_turns=3, duration_seconds=10.0
            ),
            conversation=[],
            artifacts_collected=[
                CollectedArtifact(
                    filename="report.pdf",
                    path="artifacts/report.pdf",
                    collected_at_turn=2,
                )
            ],
        )
        manifest = _save_artifacts(record, tmp_path)
        assert manifest["session_id"] == "sess-abc"
        assert len(manifest["artifacts"]) == 1
        assert manifest["artifacts"][0]["type"] == "report"

        manifest_path = tmp_path / "artifacts" / "run-manifest.json"
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text())
        assert saved == manifest
