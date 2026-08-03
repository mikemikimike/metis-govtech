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

from metis.engine.simulation.types import _EXPERIMENT_VERSION, Experiment

ENGINE_PKG = Path(__file__).resolve().parents[3] / "packages" / "engine"
SCHEMA_DIR = ENGINE_PKG / "schemas"
EXAMPLES_DIR = ENGINE_PKG / "example-experiment"

# (model, schema_file, fixture_path, version)
_CASES = [
    (
        Experiment,
        "experiment.schema.json",
        EXAMPLES_DIR / "experiment.yaml",
        _EXPERIMENT_VERSION,
    ),
]


def _load_fixture(path: Path) -> dict:
    text = path.read_text()
    data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    return data


@pytest.mark.parametrize("model,schema_file,fixture_path,version", _CASES)
def test_schema_is_fresh(model, schema_file, fixture_path, version):
    """Committed schema must match what generate_schema.py produces now."""
    schema_path = SCHEMA_DIR / schema_file
    if not schema_path.exists():
        pytest.fail(
            f"Schema file not found: {schema_path}. Run `make generate-schema`."
        )
    committed = json.loads(schema_path.read_text())
    current = model.model_json_schema()
    current["title"] = f"{model.__name__} v{version}"
    assert committed == current, (
        f"{schema_file} is stale. Run `make generate-schema` to regenerate."
    )


@pytest.mark.parametrize("model,schema_file,fixture_path,version", _CASES)
def test_fixture_validates_against_schema(model, schema_file, fixture_path, version):
    """Test fixture must conform to the JSON Schema."""
    schema_path = SCHEMA_DIR / schema_file
    if not fixture_path.exists():
        pytest.fail(f"Fixture not found: {fixture_path}")
    schema = json.loads(schema_path.read_text())
    data = _load_fixture(fixture_path)
    jsonschema.validate(instance=data, schema=schema)


@pytest.mark.parametrize("model,schema_file,fixture_path,version", _CASES)
def test_fixture_parses_with_pydantic(model, schema_file, fixture_path, version):
    """Test fixture must parse successfully with the Pydantic model."""
    if not fixture_path.exists():
        pytest.fail(f"Fixture not found: {fixture_path}")
    data = _load_fixture(fixture_path)
    obj = model.model_validate(data)
    if hasattr(obj, "id"):
        assert obj.id
    elif hasattr(obj, "tasks"):
        assert len(obj.tasks) > 0
    elif hasattr(obj, "schema_version"):
        assert obj.schema_version
    else:
        assert obj.config.persona
