"""Shared test configuration."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


def _find_repo_root() -> Path:
    """Walk up from this file to find the workspace root (contains pyproject.toml with [tool.uv.workspace])."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "uv.lock").exists():
            return parent
    raise RuntimeError("Could not find repo root")


REPO_ROOT = _find_repo_root()


@pytest.fixture
def repo_root() -> Path:
    """Path to the monorepo workspace root."""
    return REPO_ROOT


@pytest.fixture
def export_clock(monkeypatch):
    from metis.wizard.application import export_layout

    def set_time(value: datetime) -> None:
        monkeypatch.setattr(
            export_layout, "datetime", SimpleNamespace(now=lambda: value)
        )

    set_time(datetime(2026, 10, 16, 22, 30, 45))
    return set_time
