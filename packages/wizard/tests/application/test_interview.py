"""The package-owned interview settings and status copy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fixtures.profiles import research_assistant
from fixtures.scripted import ScriptedInterviewer

from metis.wizard.application import Session, interview
from metis.wizard.application.driver import StepDriver
from metis.wizard.contracts import Product, ProductProfile
from metis.wizard.contracts.session_state import SessionState, Turn
from metis.wizard.domain.permissions import SessionStep

_EXPECTED_STATUSES = {
    "clarify": "Understanding your agent…",
    "behaviours": "Shaping expected behaviours…",
    "prioritise": "Writing testable criteria…",
    "criteria": "Designing evaluator personas…",
    "personas": "Building coverage scenarios…",
    "scenarios": "Finalising your evaluation…",
    "done": "Finishing up…",
}


def _document() -> dict[str, Any]:
    value = yaml.safe_load(interview._read_config_text())
    assert isinstance(value, dict)
    return value


def _install_document(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        interview,
        "_read_config_text",
        lambda: yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
    )


def _assert_complete_interview_document_is_validated(
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[dict[str, Any]], None],
    broken_key: str,
) -> None:
    document = _document()
    change(document)
    _install_document(monkeypatch, document)

    with pytest.raises(interview.InterviewConfigError) as caught:
        interview.load_interview_config()

    message = str(caught.value)
    assert interview.INTERVIEW_FILE in message
    assert broken_key in message


def _set_settings_to_list(document: dict[str, Any]) -> None:
    document["settings"] = []


def _set_statuses_to_list(document: dict[str, Any]) -> None:
    document["statuses"] = []


def _remove_status(document: dict[str, Any]) -> None:
    del document["statuses"]["criteria"]


def _blank_status(document: dict[str, Any]) -> None:
    document["statuses"]["criteria"] = "  "


@pytest.mark.parametrize(
    ("change", "broken_key"),
    [
        (_set_settings_to_list, "settings"),
        (_set_statuses_to_list, "statuses"),
        (_remove_status, "statuses.criteria"),
        (_blank_status, "statuses.criteria"),
    ],
)
def test_interview_validation_cases(
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[dict[str, Any]], None],
    broken_key: str,
) -> None:
    _assert_complete_interview_document_is_validated(monkeypatch, change, broken_key)


def test_a_missing_interview_file_is_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(interview.resources, "files", lambda _package: tmp_path)

    with pytest.raises(interview.InterviewConfigError) as caught:
        interview.load_interview_config()

    assert interview.INTERVIEW_FILE in str(caught.value)
    assert "missing" in str(caught.value)


def test_a_wrong_interview_root_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interview, "_read_config_text", lambda: "[]")

    with pytest.raises(interview.InterviewConfigError, match="<document>"):
        interview.load_interview_config()


@pytest.mark.parametrize("value", ["5", True, 0, -1])
def test_the_clarify_limit_must_be_a_positive_non_boolean_integer(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    document = _document()
    document["settings"]["clarify_turn_cap"] = value
    _install_document(monkeypatch, document)

    with pytest.raises(
        interview.InterviewConfigError, match="settings.clarify_turn_cap"
    ):
        interview.clarify_turn_cap()


def test_every_session_step_has_the_existing_status_copy() -> None:
    config = interview.load_interview_config()

    assert {
        step.value: config.statuses[step] for step in SessionStep
    } == _EXPECTED_STATUSES


def test_the_session_facade_uses_the_interview_status_owner() -> None:
    session = Session.start(
        ProductProfile(product=Product(name="Agent", summary="", users=""))
    )

    assert session.busy_message() == _EXPECTED_STATUSES["clarify"]


def test_a_status_edit_affects_the_next_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    _install_document(monkeypatch, document)

    first = interview.status_for(SessionStep.CRITERIA)
    document["statuses"]["criteria"] = "Updated criteria status."
    second = interview.status_for(SessionStep.CRITERIA)

    assert first == _EXPECTED_STATUSES["criteria"]
    assert second == "Updated criteria status."


def test_a_limit_edit_affects_an_active_interview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["settings"]["clarify_turn_cap"] = 3
    _install_document(monkeypatch, document)
    state = SessionState(
        id="s",
        profile=research_assistant(),
        step=SessionStep.CLARIFY,
        history=[
            Turn(role="assistant", text=interview.opening_question()),
            Turn(role="user", text="the first answer"),
            Turn(role="assistant", text="question one"),
            Turn(role="assistant", text="question two"),
        ],
    )
    driver = StepDriver(interviewer=ScriptedInterviewer(clarify_questions=5))

    driver.compose(state)
    assert state.step is SessionStep.CLARIFY

    document["settings"]["clarify_turn_cap"] = 2
    driver.compose(state)

    assert state.step is SessionStep.BEHAVIOURS


def test_interview_configuration_is_a_package_resource() -> None:
    config = interview.load_interview_config()

    assert config.clarify_turn_cap > 0
    assert config.opening_question
    assert set(config.statuses) == set(SessionStep)
