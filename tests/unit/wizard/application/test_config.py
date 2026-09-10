"""The package-owned interview settings and status copy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from metis.wizard.application import config
from metis.wizard.application.driver import DriverState, StepDriver
from metis.wizard.contracts.interview_state import Turn
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.profiles import research_assistant
from tests.fixtures.wizard.scripted import ScriptedInterviewer

_EXPECTED_STATUSES = {
    "clarify": "Understanding your agent…",
    "behaviours": "Shaping expected behaviours…",
    "criteria": "Writing testable criteria…",
    "personas": "Designing evaluator personas…",
    "scenarios": "Building coverage scenarios…",
    "done": "Finishing up…",
}
_EXPECTED_WORKING_STATUS = "Working on your Interview…"


def _document() -> dict[str, Any]:
    value = yaml.safe_load(config._read_config_text())
    assert isinstance(value, dict)
    return value


def _install_document(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        config,
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

    with pytest.raises(config.ConfigError) as caught:
        config.load_config()

    message = str(caught.value)
    assert config.CONFIG_FILE in message
    assert broken_key in message


def _set_settings_to_list(document: dict[str, Any]) -> None:
    document["settings"] = []


def _set_statuses_to_list(document: dict[str, Any]) -> None:
    document["statuses"] = []


def _remove_status(document: dict[str, Any]) -> None:
    del document["statuses"]["criteria"]


def _blank_status(document: dict[str, Any]) -> None:
    document["statuses"]["criteria"] = "  "


def _remove_working_status(document: dict[str, Any]) -> None:
    del document["statuses"]["working"]


def _blank_working_status(document: dict[str, Any]) -> None:
    document["statuses"]["working"] = "  "


def _restore_removed_status(document: dict[str, Any]) -> None:
    document["statuses"]["prioritise"] = "Choosing what to measure…"


@pytest.mark.parametrize(
    ("change", "broken_key"),
    [
        (_set_settings_to_list, "settings"),
        (_set_statuses_to_list, "statuses"),
        (_remove_status, "statuses.criteria"),
        (_blank_status, "statuses.criteria"),
        (_remove_working_status, "statuses.working"),
        (_blank_working_status, "statuses.working"),
        (_restore_removed_status, "statuses.prioritise"),
    ],
)
def test_interview_validation_cases(
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[dict[str, Any]], None],
    broken_key: str,
) -> None:
    _assert_complete_interview_document_is_validated(monkeypatch, change, broken_key)


def test_a_missing_config_file_is_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config.resources, "files", lambda _package: tmp_path)

    with pytest.raises(config.ConfigError) as caught:
        config.load_config()

    assert config.CONFIG_FILE in str(caught.value)
    assert "missing" in str(caught.value)


def test_a_wrong_config_root_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_read_config_text", lambda: "[]")

    with pytest.raises(config.ConfigError, match="<document>"):
        config.load_config()


@pytest.mark.parametrize("value", ["5", True, 0, -1])
def test_the_clarify_limit_must_be_a_positive_non_boolean_integer(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    document = _document()
    document["settings"]["clarify_turn_cap"] = value
    _install_document(monkeypatch, document)

    with pytest.raises(config.ConfigError, match="settings.clarify_turn_cap"):
        config.clarify_turn_cap()


def test_every_interview_step_has_the_existing_status_copy() -> None:
    loaded = config.load_config()

    assert {
        step.value: loaded.statuses[step] for step in InterviewStep
    } == _EXPECTED_STATUSES


def test_the_general_working_status_comes_from_the_package_config() -> None:
    assert config.working_status() == _EXPECTED_WORKING_STATUS


def test_a_status_edit_affects_the_next_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    _install_document(monkeypatch, document)

    first = config.status_for(InterviewStep.CRITERIA)
    document["statuses"]["criteria"] = "Updated criteria status."
    second = config.status_for(InterviewStep.CRITERIA)

    assert first == _EXPECTED_STATUSES["criteria"]
    assert second == "Updated criteria status."


def test_a_limit_edit_affects_an_active_interview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["settings"]["clarify_turn_cap"] = 3
    _install_document(monkeypatch, document)
    state = DriverState(
        profile=research_assistant(),
        step=InterviewStep.CLARIFY,
        history=[
            Turn(role="assistant", text=config.opening_question()),
            Turn(role="user", text="the first answer"),
            Turn(role="assistant", text="question one"),
            Turn(role="assistant", text="question two"),
        ],
    )
    driver = StepDriver(interviewer=ScriptedInterviewer(clarify_questions=5))

    driver.compose(state)
    assert state.step is InterviewStep.CLARIFY

    document["settings"]["clarify_turn_cap"] = 2
    driver.compose(state)

    assert state.step is InterviewStep.BEHAVIOURS


def test_interview_configuration_is_a_package_resource() -> None:
    loaded = config.load_config()

    assert loaded.clarify_turn_cap > 0
    assert loaded.opening_question
    assert loaded.working_status
    assert set(loaded.statuses) == set(InterviewStep)
