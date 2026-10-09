"""Schema sync tests — guard the contract between code and committed artifacts.

These tests verify that the generated JSON Schema files in schemas/ stay in
sync with the Pydantic models in types.py, and that the example fixtures
remain valid against both. They catch drift that would otherwise go unnoticed
until an external consumer (IDE YAML plugin, CI jsonschema check, downstream
tooling) breaks.

This is NOT where model validation logic is tested — that lives in test_cli.py
which exercises _validate_inputs end-to-end.
"""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from metis.engine.simulation.types import _SPECIFICATION_VERSION, Specification


def _load_fixture(path: Path) -> dict:
    text = path.read_text()
    data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    return data


@pytest.fixture
def engine_pkg(repo_root: Path) -> Path:
    return repo_root / "packages" / "engine"


@pytest.fixture
def schema_dir(engine_pkg: Path) -> Path:
    return engine_pkg / "schemas"


@pytest.fixture
def examples_dir(engine_pkg: Path) -> Path:
    return engine_pkg / "example-experiment"


class TestSchemaSync:
    """Verify JSON Schema artifacts stay in sync with Pydantic models."""

    def test_schema_is_fresh(self, schema_dir: Path):
        """Committed schema must match what generate_schema.py produces now."""
        schema_path = schema_dir / "specification.schema.json"
        if not schema_path.exists():
            pytest.fail(
                f"Schema file not found: {schema_path}. Run `make generate-schema`."
            )
        committed = json.loads(schema_path.read_text())
        current = Specification.model_json_schema()
        current["title"] = f"Specification v{_SPECIFICATION_VERSION}"
        assert committed == current, (
            "specification.schema.json is stale. Run `make generate-schema` to regenerate."
        )

    def test_fixture_validates_against_schema(
        self, schema_dir: Path, examples_dir: Path
    ):
        """Test fixture must conform to the JSON Schema."""
        schema_path = schema_dir / "specification.schema.json"
        fixture_path = examples_dir / "specification.yaml"
        if not fixture_path.exists():
            pytest.fail(f"Fixture not found: {fixture_path}")
        schema = json.loads(schema_path.read_text())
        data = _load_fixture(fixture_path)
        jsonschema.validate(instance=data, schema=schema)

    def test_fixture_parses_with_pydantic(self, examples_dir: Path):
        """Test fixture must parse successfully with the Pydantic model."""
        pytest.importorskip(
            "playwright",
            reason="example-experiment uses OrcaPlaywrightRunnerFactory (requires playwright extra)",
        )
        fixture_path = examples_dir / "specification.yaml"
        if not fixture_path.exists():
            pytest.fail(f"Fixture not found: {fixture_path}")
        data = _load_fixture(fixture_path)
        obj = Specification.model_validate(data)
        assert obj.id
