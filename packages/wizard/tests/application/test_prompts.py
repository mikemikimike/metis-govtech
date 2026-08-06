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
from metis.wizard.application.interview import opening_question
from metis.wizard.contracts import Product, ProductProfile
from metis.wizard.contracts.session_state import Turn
from metis.wizard.domain.applier import apply
from metis.wizard.domain.patch import Patch, PatchOp

_BASELINE_SHA256 = {
    "system": "75e2c982353772cef208981bd54b16602eb3b292af1ec29628f4bc777edd73c7",
    "clarify": "3ddcfc6605b51d3b15670b83e4599e0406c8a92361c56ab4b91544fbf403e94d",
    "behaviours": "baf62840018a66b39b0cc9329ead2e4368e3e73e8f6456a6d7279e52953a3ebb",
    "criteria": "1bcde8c70f5ecaf6cf485a4b4544a23214e05a39ad8152296d0e71680dd26c65",
    "personas": "a6a490ca08ff164e69e6de8d108efad53030a2a3233072f3b183878bbac2d552",
    "scenarios": "1c15458b03c450df20947533fcf9299e3f9aea4e50e367cd64c6bcb618882004",
    "chat": "3782bc73dfd97c24aff3f861ff7970095d7f03618b22bdfbb7d7e3f8304cf2e6",
    "suggest_criterion": (
        "906965f23d9fb1870742a61f8ac597dd5e4df9d113bfac6dd94140be1919a99b"
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

    template_name = "clarify_product" if name == "clarify" else name
    document["model_calls"][template_name] += "\nFIRST EDIT"
    first = _calls_for_name(name, profile)
    document["model_calls"][template_name] = document["model_calls"][
        template_name
    ].replace("FIRST EDIT", "SECOND EDIT")
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
        "clarify_product",
        "clarify_machinery",
        "behaviours",
        "criteria",
        "personas",
        "scenarios",
        "chat",
        "suggest_criterion",
    }


def test_clarify_has_distinct_product_and_machinery_phases() -> None:
    empty = ProductProfile(product=Product(name="", users="", summary=""))

    product = prompts.clarify(empty, [], "product")
    machinery = prompts.clarify(research_assistant(), [], "machinery")

    assert product.name == machinery.name == "clarify"
    assert "tools, failures, memory or delegation yet." in product.user
    assert "taking over this product from another busy product manager" in product.user
    assert "Start wide" in product.user
    assert "reveal the most breadth" in product.user
    assert "clarify question 1 of 5" in product.user
    assert "product is established" in machinery.user
    assert "the handover is not" in machinery.user
    assert "high-leverage question" in machinery.user
    assert "question that invites an overview" in machinery.user
    assert "clarify question 1 of 5" in machinery.user
    assert "stop broad capability" in machinery.user
    assert "one agentic behaviour instead" in machinery.user
    assert "coordinates specialists" in machinery.user
    assert "Do not drill into one file or output format" in machinery.user


def test_clarify_prompt_reports_the_late_question_position() -> None:
    history = [
        Turn(role="assistant", text=opening_question()),
        Turn(role="user", text="The opening answer."),
        Turn(role="assistant", text="Question one?"),
        Turn(role="user", text="Answer one."),
        Turn(role="assistant", text="Question two?"),
        Turn(role="user", text="Answer two."),
        Turn(role="assistant", text="Question three?"),
        Turn(role="user", text="Answer three."),
    ]

    prompt = prompts.clarify(research_assistant(), history, "machinery")

    assert "This is clarify question 4 of 5." in prompt.user


def test_later_prompts_receive_product_detail_with_line_breaks() -> None:
    profile = research_assistant()
    profile.product.detail = "First line.\nSecond line."

    prompt = prompts.scenarios(profile)

    assert "First line.\\nSecond line." in prompt.user
