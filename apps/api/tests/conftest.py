"""Shared fixtures for the API door tests.

The API tests reuse the wizard's own offline corridor — the `ScriptedInterviewer`, the `walk`
driver and the hand-authored profiles — so a door test proves the HTTP adapter preserves wizard
behaviour without re-scripting it. Those fixtures live under the wizard package's test tree, so
this conftest puts that tree on `sys.path` before importing them.

Every client is built over a fresh `create_app()` with the wizard dependencies overridden to the
scripted pair, so no test ever constructs the real gateway or reaches the network.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_WIZARD_TESTS = Path(__file__).resolve().parents[3] / "packages" / "wizard" / "tests"
if str(_WIZARD_TESTS) not in sys.path:
    sys.path.insert(0, str(_WIZARD_TESTS))

from fixtures.scripted import (  # noqa: E402  (path set up above)
    ScriptedInterviewer,
    ScriptedMatcher,
)

from metis.api.main import create_app  # noqa: E402
from metis.wizard import InterviewRequest, handle_interview  # noqa: E402


def scripted_interview_handler(interviewer: object | None = None):
    """Build the public Interview seam over a fully offline scripted pair."""
    provider = interviewer or ScriptedInterviewer()
    matcher = ScriptedMatcher()

    def interview(body: InterviewRequest):
        return handle_interview(body, interviewer=provider, matcher=matcher)

    return interview


@pytest.fixture
def make_client() -> Callable[..., TestClient]:
    """Build a TestClient over its own fresh app, with the scripted dependencies injected.

    A factory rather than one client, because the cross-instance test needs two apps and some
    tests want their own interviewer to inspect afterwards.
    """

    def _make(
        interviewer: object | None = None, *, raise_server_exceptions: bool = True
    ) -> TestClient:
        app = create_app(interview_handler=scripted_interview_handler(interviewer))
        return TestClient(app, raise_server_exceptions=raise_server_exceptions)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
