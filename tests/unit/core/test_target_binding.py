"""TargetBinding: the hand-written file that binds an app to the generic HTTP runner."""

import pytest
from pydantic import ValidationError

from metis.core.target_binding import TargetBinding


def _minimal(**overrides):
    data = {
        "schema_version": 1,
        "identity": {"name": "App"},
        "transport": "http",
        "spec_url": "https://app.example/openapi.json",
    }
    data.update(overrides)
    return data


def test_minimal_binding_takes_defaults():
    binding = TargetBinding.model_validate(_minimal())
    assert binding.tls_verify is True
    assert binding.auth is None
    assert binding.secret_headers == []
    assert binding.submissions == []
    assert binding.forbidden_calls == []
    assert binding.preflight_reads == []
    assert binding.advice.notes == ""
    assert binding.advice.limits is None


def test_env_references_are_kept_as_written(monkeypatch):
    monkeypatch.delenv("APP_URL", raising=False)
    binding = TargetBinding.model_validate(_minimal(spec_url="${APP_URL}/openapi.json"))
    assert binding.spec_url == "${APP_URL}/openapi.json"


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth": {"secret_env": "sk-live-AbC123"}},
        {
            "secret_headers": [
                {"match": "POST /chat", "header": "X-Key", "env": "sk-live-AbC123"}
            ]
        },
    ],
)
def test_secret_value_in_place_of_env_name_is_rejected_without_echo(overrides):
    with pytest.raises(ValidationError) as error:
        TargetBinding.model_validate(_minimal(**overrides))
    assert "sk-live-AbC123" not in str(error.value)


@pytest.mark.parametrize(
    "pattern",
    [
        "post /chat",
        "POST chat",
        "POST  /chat",
        "FETCH /chat",
        "/chat",
        "DELETE /api/v1/sessions/{sessionId}",
        "POST /chat?x=1",
        "GET /chat#top",
    ],
)
def test_malformed_call_pattern_rejected(pattern):
    with pytest.raises(ValidationError):
        TargetBinding.model_validate(_minimal(forbidden_calls=[pattern]))


@pytest.mark.parametrize(
    "pattern", ["DELETE /api/v1/**", "* /admin/*", "POST /api/v1/chat"]
)
def test_call_patterns_accepted(pattern):
    binding = TargetBinding.model_validate(
        _minimal(submissions=[pattern], forbidden_calls=[pattern])
    )
    assert binding.forbidden_calls == [pattern]
    assert binding.submissions == [pattern]


def test_browser_transport_rejected():
    with pytest.raises(ValidationError) as error:
        TargetBinding.model_validate(
            _minimal(transport="browser", start_url="https://app.example")
        )
    assert "transport" in str(error.value)


@pytest.mark.parametrize(
    "overrides",
    [{"forbiden_calls": []}, {"notes": "x"}, {"advice": {"limits": {"burst": 3}}}],
)
def test_unknown_keys_rejected(overrides):
    with pytest.raises(ValidationError):
        TargetBinding.model_validate(_minimal(**overrides))


@pytest.mark.parametrize("version", [None, 2])
def test_schema_version_is_required_and_pinned(version):
    data = _minimal()
    if version is None:
        del data["schema_version"]
    else:
        data["schema_version"] = version
    with pytest.raises(ValidationError):
        TargetBinding.model_validate(data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"advice": {"limits": {"submit_per_minute": 0}}},
        {"preflight_reads": ["api/v1/usage"]},
        {"preflight_reads": ["/api/v1/usage?days=7"]},
        {"preflight_reads": ["/api/v1/users/{userId}"]},
        {"identity": {"name": ""}},
        {"secret_headers": [{"match": "POST /chat", "header": "X Key", "env": "KEY"}]},
    ],
)
def test_invalid_values_rejected(overrides):
    with pytest.raises(ValidationError):
        TargetBinding.model_validate(_minimal(**overrides))
