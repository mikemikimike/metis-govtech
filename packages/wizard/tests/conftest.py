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
