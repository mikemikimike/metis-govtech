"""Schema sync tests for report.json — same pattern as test_schema.py."""

import json
from pathlib import Path

import jsonschema
import pytest

from metis.insights._models import _REPORT_VERSION, Report


@pytest.fixture
def insights_pkg(repo_root: Path) -> Path:
    return repo_root / "packages" / "insights"


@pytest.fixture
def schema_dir(insights_pkg: Path) -> Path:
    return insights_pkg / "schemas"


class TestReportSchemaSync:
    def test_schema_is_fresh(self, schema_dir: Path):
        """Committed report schema must match what the model produces now."""
        schema_path = schema_dir / "report.schema.json"
        if not schema_path.exists():
            pytest.fail(
                f"Schema file not found: {schema_path}. Run `make generate-schema`."
            )
        committed = json.loads(schema_path.read_text())
        current = Report.model_json_schema(by_alias=True)
        current["title"] = f"Report v{_REPORT_VERSION}"
        assert committed == current, (
            "report.schema.json is stale. Run `make generate-schema` to regenerate."
        )

    def test_fixture_validates_against_schema(self, schema_dir: Path, repo_root: Path):
        """Real report.json must conform to the JSON Schema."""
        schema_path = schema_dir / "report.schema.json"
        fixture_path = (
            repo_root
            / "experiments"
            / "orca-eval-20260827-222704"
            / "reports"
            / "report.json"
        )
        if not fixture_path.exists():
            pytest.skip("sample report.json not available")
        schema = json.loads(schema_path.read_text())
        data = json.loads(fixture_path.read_text())
        jsonschema.validate(instance=data, schema=schema)

    def test_fixture_parses_with_pydantic(self, repo_root: Path):
        """Real report.json must parse with the Pydantic model."""
        fixture_path = (
            repo_root
            / "experiments"
            / "orca-eval-20260827-222704"
            / "reports"
            / "report.json"
        )
        if not fixture_path.exists():
            pytest.skip("sample report.json not available")
        data = json.loads(fixture_path.read_text())
        report = Report.model_validate(data)
        assert report.target
