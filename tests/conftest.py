"""Shared test configuration."""

from pathlib import Path

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
