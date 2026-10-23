"""The example target binding for Orca's API, and the README that shows it (#481)."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.core.target_binding import TargetBinding
from metis.engine.simulation.gen_2.binding import load_target_binding
from metis.engine.simulation.gen_2.runners.rules import ToolRefused, check_call

ENGINE = Path(__file__).resolve().parents[3] / "packages" / "engine"
EXAMPLE = ENGINE / "examples"
BINDING = EXAMPLE / "orca-api-http-simple1" / "orca-api.yaml"
README = ENGINE / "src/metis/engine/simulation/gen_2/README.md"
SCHEMA = EXAMPLE.parents[1] / "core" / "schemas" / "target-binding.schema.json"


@pytest.fixture
def binding(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCA_API_URL", "https://orca.example:7443/api/v1")
    monkeypatch.setenv("ORCA_API_KEY", "key-1")
    return load_target_binding(EXAMPLE / "orca-api-http-simple1", "orca-api.yaml")


def test_the_example_loads_and_expands_its_spec_url(binding) -> None:
    assert binding.binding.identity.name == "Orca"
    assert binding.spec_url == "https://orca.example:7443/api/v1/openapi.json"
    assert binding.binding.tls_verify is False
    assert binding.secret("ORCA_API_KEY") is not None


def test_the_example_points_editors_at_the_published_schema() -> None:
    first = BINDING.read_text(encoding="utf-8").splitlines()[0]

    assert first.startswith("# yaml-language-server: $schema=")
    relative = first.partition("$schema=")[2]
    assert (BINDING.parent / relative).resolve() == SCHEMA.resolve()


@pytest.mark.parametrize(
    ("method", "path"),
    [("DELETE", "/api/v1/sessions/s-1"), ("DELETE", "/api/v1/files/f-1")],
)
def test_the_example_forbids_the_calls_orca_should_not_get(
    binding, method: str, path: str
) -> None:
    with pytest.raises(ToolRefused, match="forbidden"):
        check_call(method, path, binding.binding.forbidden_calls)


def test_the_example_allows_the_calls_a_trial_needs(binding) -> None:
    for method, path in [
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/chat/cancel"),
        ("POST", "/api/v1/files"),
        ("GET", "/api/v1/files/f-1/content"),
    ]:
        check_call(method, path, binding.binding.forbidden_calls)


def test_the_example_matches_the_model_it_is_written_for() -> None:
    import yaml

    TargetBinding.model_validate(yaml.safe_load(BINDING.read_text(encoding="utf-8")))


def test_the_readme_shows_the_example_exactly() -> None:
    assert BINDING.read_text(encoding="utf-8") in README.read_text(encoding="utf-8")


def test_the_readme_says_it_has_only_been_tried_on_orca() -> None:
    assert "Orca's API only" in README.read_text(encoding="utf-8")


WEB_BINDING = EXAMPLE / "targets" / "web-chat.yaml"


@pytest.fixture
def web_binding(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAT_URL", "https://chat.example/")
    monkeypatch.setenv("CHAT_USER", "alice")
    monkeypatch.setenv("CHAT_PASSWORD", "SENTINEL-PASSWORD")
    return load_target_binding(EXAMPLE, "targets/web-chat.yaml", "browser")


def test_the_browser_example_loads_and_reads_its_login_secrets(web_binding) -> None:
    assert web_binding.start_url == "https://chat.example/"
    assert web_binding.spec_url is None
    assert web_binding.secret("CHAT_PASSWORD") is not None
    assert "{{secret:CHAT_USER}}" in (web_binding.binding.login.note or "")


def test_the_browser_example_points_editors_at_the_published_schema() -> None:
    first = WEB_BINDING.read_text(encoding="utf-8").splitlines()[0]

    relative = first.partition("$schema=")[2]
    assert (WEB_BINDING.parent / relative).resolve() == SCHEMA.resolve()


def test_the_readme_shows_the_browser_example_exactly() -> None:
    assert WEB_BINDING.read_text(encoding="utf-8") in README.read_text(encoding="utf-8")


def test_the_readme_says_the_browser_runner_has_never_met_a_live_page() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Never run against a live page" in text
    assert "`end_chat` does nothing" in text
