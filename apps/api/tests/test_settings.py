from __future__ import annotations

import pytest

from metis.api.cli import _load_env
from metis.api.settings import Settings, SettingsError


def test_settings_read_the_shared_interview_provider_names(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("INTERVIEW_MODEL", "interview-model")

    assert Settings.from_env() == Settings(
        api_key="test-key",
        base_url="https://gateway.example/v1",
        interview_model="interview-model",
    )


def test_settings_name_missing_interview_provider_values(monkeypatch) -> None:
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "INTERVIEW_MODEL"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(
        SettingsError,
        match="OPENAI_API_KEY, OPENAI_BASE_URL, INTERVIEW_MODEL",
    ):
        Settings.from_env()


def test_cli_loads_the_current_project_environment(monkeypatch, tmp_path) -> None:
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "INTERVIEW_MODEL"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=file-key\n"
        "OPENAI_BASE_URL=https://file.example/v1\n"
        "INTERVIEW_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    _load_env()

    assert Settings.from_env() == Settings(
        api_key="file-key",
        base_url="https://file.example/v1",
        interview_model="file-model",
    )
