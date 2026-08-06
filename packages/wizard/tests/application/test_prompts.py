"""The prompt catalogue, its validation, and its byte-stable extraction baseline."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fixtures.profiles import research_assistant

from metis.wizard.application import prompts
from metis.wizard.contracts.session_state import Turn
from metis.wizard.domain.applier import apply
from metis.wizard.domain.patch import Patch, PatchOp

_BASELINE_SHA256 = {
    "system": "75e2c982353772cef208981bd54b16602eb3b292af1ec29628f4bc777edd73c7",
    "clarify": "f7ae00848040b4354ba82301ddfed160159bcbf27afd750bd58ec19bddb70c17",
    "behaviours": "3fd9c987a4ed56fa35ab1cf4e729996660df4aaaab8427264fec770d1583d0b5",
    "criteria": "58d9727ad09c5d54723591748bc768211fe90d489d40eaba990d73c1ac51792b",
    "personas": "4147073a3664f6b06368f2fbff68ec5290a9c07036e1471cd06b92f24588624c",
    "scenarios": "dfcddd57e96f14674962b5b0550fa70c27a654f24a08fe27a8827be9b4739d5d",
    "chat": "f38fcff71534bb03f9ba2ce60c1a557174079edb14c3215ae66f61c32a0bb096",
    "suggest_criterion": (
        "3b29d0b4206a02826eaa06945bbedc2909f48dfe008df498c9821cde0664441a"
    ),
}


def _calls() -> dict[str, prompts.ModelPrompt]:
    profile = research_assistant()
    history = [
        Turn(role="assistant", text="What does it do?"),
        Turn(role="user", text="It answers questions."),
    ]
    return {
        "clarify": prompts.clarify(profile, history),
        "behaviours": prompts.behaviours(profile, history),
        "criteria": prompts.criteria(profile),
        "personas": prompts.personas(profile),
        "scenarios": prompts.scenarios(profile),
        "chat": prompts.chat(profile, "criteria", "Make this stricter", "EB-1"),
        "suggest_criterion": prompts.suggest_criterion(profile, "EB-1"),
    }


def _document() -> dict[str, Any]:
    value = yaml.safe_load(prompts._read_catalog_text())
    assert isinstance(value, dict)
    return value


def _install_document(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        prompts,
        "_read_catalog_text",
        lambda: yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
    )


def test_prompt_extraction_preserves_every_byte() -> None:
    calls = _calls()
    actual = {
        "system": hashlib.sha256(calls["clarify"].system.encode()).hexdigest(),
        **{
            name: hashlib.sha256(prompt.user.encode()).hexdigest()
            for name, prompt in calls.items()
        },
    }

    assert actual == _BASELINE_SHA256
    assert {prompt.name for prompt in calls.values()} == set(calls)


def _assert_complete_catalogue_is_validated(
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[dict[str, Any]], None],
    broken_key: str,
) -> None:
    document = _document()
    change(document)
    _install_document(monkeypatch, document)

    with pytest.raises(prompts.PromptCatalogError) as caught:
        prompts.criteria(research_assistant())

    message = str(caught.value)
    assert prompts.PROMPTS_FILE in message
    assert broken_key in message


def _set_system_to_list(document: dict[str, Any]) -> None:
    document["system"] = []


def _remove_criteria(document: dict[str, Any]) -> None:
    del document["model_calls"]["criteria"]


def _blank_scenarios(document: dict[str, Any]) -> None:
    document["model_calls"]["scenarios"] = "  "


def _invalid_template(document: dict[str, Any]) -> None:
    document["model_calls"]["criteria"] = "bad $"


def _unsupported_placeholder(document: dict[str, Any]) -> None:
    document["model_calls"]["criteria"] = "$profile $unknown"


@pytest.mark.parametrize(
    ("change", "broken_key"),
    [
        (_set_system_to_list, "system"),
        (_remove_criteria, "model_calls.criteria"),
        (_blank_scenarios, "model_calls.scenarios"),
        (_invalid_template, "model_calls.criteria"),
        (_unsupported_placeholder, "model_calls.criteria"),
    ],
)
def test_catalogue_validation_cases(
    monkeypatch: pytest.MonkeyPatch,
    change: Callable[[dict[str, Any]], None],
    broken_key: str,
) -> None:
    _assert_complete_catalogue_is_validated(monkeypatch, change, broken_key)


def test_a_missing_catalogue_file_is_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(prompts.resources, "files", lambda _package: tmp_path)

    with pytest.raises(prompts.PromptCatalogError) as caught:
        prompts.load_prompt_catalog()

    assert prompts.PROMPTS_FILE in str(caught.value)
    assert "missing" in str(caught.value)


def test_a_wrong_catalogue_root_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "_read_catalog_text", lambda: "[]")

    with pytest.raises(prompts.PromptCatalogError, match="<document>"):
        prompts.load_prompt_catalog()


def test_an_unsupplied_placeholder_is_rejected() -> None:
    with pytest.raises(prompts.PromptCatalogError, match="model_calls.criteria"):
        prompts._substitute("$profile", "model_calls.criteria", {})


def test_json_braces_and_an_escaped_dollar_are_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["model_calls"]["criteria"] = 'value: {"name": "example"}; $$5; $profile'
    _install_document(monkeypatch, document)

    result = prompts.criteria(research_assistant()).user

    assert 'value: {"name": "example"}; $5;' in result
    assert result.endswith("}")


@pytest.mark.parametrize(
    "name",
    [
        "clarify",
        "behaviours",
        "criteria",
        "personas",
        "scenarios",
        "chat",
        "suggest_criterion",
    ],
)
def test_each_model_call_reloads_before_composition(
    monkeypatch: pytest.MonkeyPatch, name: prompts.ModelCall
) -> None:
    document = _document()
    _install_document(monkeypatch, document)
    profile = research_assistant()

    document["model_calls"][name] += "\nFIRST EDIT"
    first = _calls_for_name(name, profile)
    document["model_calls"][name] = document["model_calls"][name].replace(
        "FIRST EDIT", "SECOND EDIT"
    )
    second = _calls_for_name(name, profile)

    assert first.user.endswith("FIRST EDIT")
    assert second.user.endswith("SECOND EDIT")


def _calls_for_name(name: prompts.ModelCall, profile) -> prompts.ModelPrompt:
    history = [Turn(role="assistant", text="question")]
    composers = {
        "clarify": lambda: prompts.clarify(profile, history),
        "behaviours": lambda: prompts.behaviours(profile, history),
        "criteria": lambda: prompts.criteria(profile),
        "personas": lambda: prompts.personas(profile),
        "scenarios": lambda: prompts.scenarios(profile),
        "chat": lambda: prompts.chat(profile, "criteria", "edit", None),
        "suggest_criterion": lambda: prompts.suggest_criterion(profile, "EB-1"),
    }
    return composers[name]()


def test_the_system_and_user_messages_share_one_catalogue_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    _install_document(monkeypatch, document)
    reads = 0
    original = prompts._read_catalog_text

    def read_once() -> str:
        nonlocal reads
        reads += 1
        return original()

    monkeypatch.setattr(prompts, "_read_catalog_text", read_once)
    prompt = prompts.criteria(research_assistant())

    assert reads == 1
    assert prompt.system
    assert prompt.user


def test_the_primer_reloads_for_the_next_complete_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = _document()
    (tmp_path / prompts.PROMPTS_FILE).write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    )
    primer_path = tmp_path / prompts.PRIMER_FILE
    primer_path.write_text("FIRST PRIMER")
    monkeypatch.setattr(prompts.resources, "files", lambda _package: tmp_path)

    first = prompts.criteria(research_assistant())
    primer_path.write_text("SECOND PRIMER")
    second = prompts.criteria(research_assistant())

    assert first.system.endswith("FIRST PRIMER")
    assert second.system.endswith("SECOND PRIMER")


def test_configured_patch_rules_do_not_change_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["system"]["patch_rules"] = "The model may set priority."
    _install_document(monkeypatch, document)
    profile = research_assistant()

    assert "The model may set priority." in prompts.criteria(profile).system
    result = apply(
        profile,
        [
            Patch(
                op=PatchOp.SET,
                path="tasks[T-1].behaviours[EB-1].priority",
                value=False,
            )
        ],
    )

    assert result.applied == []
    assert len(result.rejected) == 1
    assert profile.behaviour("EB-1").priority is True  # type: ignore[union-attr]


def test_prompt_catalogue_is_a_package_resource() -> None:
    catalog = prompts.load_prompt_catalog()

    assert catalog.patch_rules
    assert set(catalog.model_calls) == {
        "clarify",
        "behaviours",
        "criteria",
        "personas",
        "scenarios",
        "chat",
        "suggest_criterion",
    }
