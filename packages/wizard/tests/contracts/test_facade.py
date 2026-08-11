"""The stable headless import surface."""

import json
from pathlib import Path

from metis.wizard import (
    AnyRequest,
    CompilationError,
    ProductProfile,
    Session,
    SessionState,
    UserResponse,
    WizardRequest,
    compile_experiment,
    render_review,
    write_experiment,
    write_review,
)


def test_headless_facade_exports_session_contract_and_compiler() -> None:
    assert Session
    assert SessionState
    assert ProductProfile
    assert WizardRequest
    assert UserResponse
    assert AnyRequest
    assert CompilationError
    assert compile_experiment
    assert render_review
    assert write_experiment
    assert write_review


def test_session_fixture_loads_through_the_facade(fixtures_dir: Path) -> None:
    """The stable facade preserves the persisted wire shape and concrete request type."""
    from metis.wizard import SessionState
    from metis.wizard.contracts import ChoiceRequest

    path = fixtures_dir / "session_fixture.json"
    raw = json.loads(path.read_text())
    state = SessionState.load(path)

    expected_profile = dict(raw["profile"])
    expected_product = dict(expected_profile["product"])
    expected_product.pop("architecture")
    expected_product["detail"] = ""
    expected_profile["product"] = expected_product
    assert state.profile.model_dump(mode="json") == expected_profile
    assert state.step.value == raw["step"]
    assert [turn.model_dump(mode="json") for turn in state.history] == raw["history"]
    assert isinstance(state.pending, ChoiceRequest)
    assert [r.model_dump(mode="json") for r in state.requests] == raw["requests"]
