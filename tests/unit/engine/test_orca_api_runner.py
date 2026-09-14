"""Tests for the Orca API runner package."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from metis.engine.simulation.runners.orca_api import (
    OrcaApiRunner,
    OrcaApiRunnerConfig,
    OrcaApiRunnerFactory,
)
from metis.engine.simulation.runners.orca_api._fixtures import content_type_for
from metis.engine.simulation.types import (
    ButtonClickAction,
    FormFillAction,
    Observation,
    UploadFileAction,
)


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
        assert config.api_key.get_secret_value() == "test-key"
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


def _make_runner(tmp_path, fixtures=()):
    config = OrcaApiRunnerConfig(
        base_url="https://orca.example.com", api_key="test-key"
    )
    client = httpx.AsyncClient(base_url="https://orca.example.com")
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    runner = OrcaApiRunner(client, config, fixtures_dir=fixtures_dir, run_dir=run_dir)
    runner._fixtures = list(fixtures)
    return runner, fixtures_dir


class TestBuildSubmitBody:
    @pytest.mark.asyncio
    async def test_form_fill_keys_on_slot_id(self, tmp_path) -> None:
        runner, _ = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [{"id": "q1", "type": "text", "label": "Q1"}],
        }
        body = await runner._build_submit_body(
            "prose", [FormFillAction(slot_id="q1", value="answer")]
        )
        assert isinstance(body, dict)
        assert body["formAnswers"] == {"q1": "answer"}
        assert "message" not in body

    @pytest.mark.asyncio
    async def test_upload_naming_non_fixture_is_loud_error(self, tmp_path) -> None:
        runner, _ = _make_runner(tmp_path, fixtures=["sales.csv"])
        result = await runner._build_submit_body(
            "hi", [UploadFileAction(slot_id="ghost.csv", filename="ghost.csv")]
        )
        assert isinstance(result, Observation)
        assert result.errors and "ghost.csv" in result.errors[0]

    @pytest.mark.asyncio
    async def test_upload_missing_file_is_loud_error(self, tmp_path) -> None:
        runner, _ = _make_runner(tmp_path, fixtures=["sales.csv"])
        # "sales.csv" is a scenario fixture but no file was written to disk.
        result = await runner._build_submit_body(
            "hi", [UploadFileAction(slot_id="sales.csv", filename="sales.csv")]
        )
        assert isinstance(result, Observation)
        assert result.errors and "sales.csv" in result.errors[0]

    @pytest.mark.asyncio
    async def test_valid_upload_attaches_file(self, tmp_path, monkeypatch) -> None:
        runner, fixtures_dir = _make_runner(tmp_path, fixtures=["sales.csv"])
        (fixtures_dir / "sales.csv").write_text("a,b\n1,2\n")

        async def fake_file_id(name, path):
            return "file-123"

        monkeypatch.setattr(runner._fixture_library, "file_id", fake_file_id)
        body = await runner._build_submit_body(
            "hi", [UploadFileAction(slot_id="sales.csv", filename="sales.csv")]
        )
        assert isinstance(body, dict)
        assert body["files"] == ["file-123"]
        assert body["message"] == "hi"

    @pytest.mark.asyncio
    async def test_button_click_is_skipped_message_sent(self, tmp_path) -> None:
        runner, _ = _make_runner(tmp_path)
        body = await runner._build_submit_body(
            "hello", [ButtonClickAction(slot_id="run")]
        )
        assert isinstance(body, dict)
        assert body["message"] == "hello"
        assert "files" not in body and "formAnswers" not in body
