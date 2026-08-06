"""Shared fixtures for the wizard tests.

`FIXTURES` is where hand-authored profiles and golden files live. A hand-authored
`ProductProfile` is a first-class test input: the profile model deliberately requires no
session, no step and no history, so a fixture can be written by hand and compiled.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def disable_external_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the test suite from sending model content to a real Langfuse instance."""
    for name in (
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
