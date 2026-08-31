"""Tests for the Orca API runner package."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.engine.simulation.runners.orca_api import (
    OrcaApiRunnerConfig,
    OrcaApiRunnerFactory,
)
from metis.engine.simulation.runners.orca_api._fixtures import content_type_for


class TestOrcaApiRunnerConfig:
    def test_load_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("poll_interval_ms: 5000\nsubmit_rpm: 10\n")
        monkeypatch.setenv("ORCA_API_URL", "https://orca.example.com")
        monkeypatch.setenv("ORCA_API_KEY", "test-key")
        config = OrcaApiRunnerConfig.load(config_yaml)
        assert config.base_url == "https://orca.example.com"
        assert config.api_key == "test-key"
        assert config.poll_interval_ms == 5000
        assert config.submit_rpm == 10

    def test_missing_env_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("{}")
        monkeypatch.delenv("ORCA_API_URL", raising=False)
        monkeypatch.delenv("ORCA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="missing required environment"):
            OrcaApiRunnerConfig.load(config_yaml)

    def test_invalid_url_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("{}")
        monkeypatch.setenv("ORCA_API_URL", "not-a-url")
        monkeypatch.setenv("ORCA_API_KEY", "key")
        with pytest.raises(ValueError, match="must be an http"):
            OrcaApiRunnerConfig.load(config_yaml)


class TestOrcaApiRunnerFactory:
    def test_factory_init_with_config(self) -> None:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
        )
        factory = OrcaApiRunnerFactory(config)
        assert factory.retry_defaults == (2, 5.0)

    def test_factory_satisfies_protocol(self) -> None:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
        )
        factory = OrcaApiRunnerFactory(config)
        assert callable(getattr(factory, "start", None))
        assert callable(getattr(factory, "create", None))
        assert callable(getattr(factory, "close", None))

    def test_resolver_finds_factory(self) -> None:
        from metis.engine.simulation.runner_resolver import resolve_runner_factory

        cls = resolve_runner_factory(
            "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
        )
        assert cls is OrcaApiRunnerFactory


class TestContentTypeFor:
    @pytest.mark.parametrize(
        "suffix, expected",
        [
            (".pdf", "application/pdf"),
            (".csv", "text/csv"),
            (".png", "image/png"),
            (".json", "application/json"),
        ],
    )
    def test_known_types(self, suffix: str, expected: str, tmp_path: Path) -> None:
        path = tmp_path / f"file{suffix}"
        path.touch()
        assert content_type_for(path) == expected
