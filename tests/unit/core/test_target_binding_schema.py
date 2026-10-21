"""The published target binding schema, and the Orca binding validated against it."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from metis.core.target_binding import TargetBinding


@pytest.fixture
def schema(repo_root: Path) -> dict:
    path = repo_root / "packages/core/schemas/target-binding.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def orca(repo_root: Path) -> dict:
    path = repo_root / "tests/fixtures/target_binding/orca-api.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_orca_binding_validates_against_model(orca):
    binding = TargetBinding.model_validate(orca)
    assert binding.spec_url == "${ORCA_API_URL}/openapi.json"
    assert binding.tls_verify is False
    assert binding.auth is not None and binding.auth.secret_env == "ORCA_API_KEY"
    assert binding.secret_headers[0].env == "ORCA_PLATFORM_AI_KEY"
    assert binding.submissions == ["POST /api/v1/chat"]
    assert binding.forbidden_calls == ["DELETE /api/v1/**", "POST /api/v1/chat/cancel"]
    assert binding.preflight_reads == ["/api/v1/usage"]
    assert binding.advice.limits is not None
    assert binding.advice.limits.submit_per_minute == 6


def test_orca_binding_validates_against_published_schema(schema, orca):
    jsonschema.validate(instance=orca, schema=schema)


def test_published_schema_marks_advice(schema):
    assert schema["title"] == "TargetBinding v1"
    assert schema["$defs"]["Advice"]["description"].startswith(
        "Advice for the runner agent"
    )


def test_published_schema_rejects_secret_value(schema, orca):
    orca["auth"]["secret_env"] = "sk-live-AbC123"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=orca, schema=schema)
