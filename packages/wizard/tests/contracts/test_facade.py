"""The stable headless import surface."""

import json
from pathlib import Path

from metis.wizard import (
    AnyRequest,
    CompilationError,
    Interview,
    InterviewState,
    ProductProfile,
    UserResponse,
    WizardRequest,
    compile_experiment,
    render_review,
    write_experiment,
    write_review,
)


def test_headless_facade_exports_interview_contract_and_compiler() -> None:
    assert Interview
    assert InterviewState
    assert ProductProfile
    assert WizardRequest
    assert UserResponse
    assert AnyRequest
    assert CompilationError
    assert compile_experiment
    assert render_review
    assert write_experiment
    assert write_review


def test_interview_fixture_loads_through_the_facade(fixtures_dir: Path) -> None:
    """The stable facade preserves the persisted wire shape and concrete request type."""
    from metis.wizard import InterviewState
    from metis.wizard.contracts import ChoiceRequest

    path = fixtures_dir / "interview_state_fixture.json"
    raw = json.loads(path.read_text())
    state = InterviewState.load(path)

    assert state.profile.model_dump(mode="json") == raw["profile"]
    assert state.step.value == raw["step"]
    assert [turn.model_dump(mode="json") for turn in state.history] == raw["history"]
    assert isinstance(state.pending, ChoiceRequest)
    assert len(state.requests) == len(raw["requests"])
    assert state.requests[0].prompt == raw["requests"][0]["prompt"]
    assert [o.label for o in state.pending.options] == [
        o["label"] for o in raw["requests"][0]["options"]
    ]
    assert state.user_typed == set(raw["user_typed"])
    assert state.issued_ids == set(raw["issued_ids"])
