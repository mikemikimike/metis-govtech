"""The prompt catalogue, its validation, and its composition contracts."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from metis.wizard.application import prompts
from metis.wizard.application.config import opening_question
from metis.wizard.contracts import InterviewDocument, Product, ProductProfile
from metis.wizard.contracts.interview_state import Perspective, Turn
from metis.wizard.domain.applier import apply
from metis.wizard.domain.patch import Patch, PatchOp
from tests.fixtures.wizard.context import interview_context
from tests.fixtures.wizard.profiles import orca_handover, research_assistant

PERSPECTIVES = Path("packages/wizard/src/metis/wizard/application/perspectives")


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


def _perspective_text(name: str) -> str:
    """The on-disk perspective body, exactly as composition embeds it."""
    return (PERSPECTIVES / f"{name}.md").read_text(encoding="utf-8").strip()


def _xml_content(message: str, tag: str) -> str:
    opening = f"<{tag}>"
    closing = f"</{tag}>"
    start = message.rfind(opening)
    assert start >= 0
    start += len(opening)
    end = message.index(closing, start)
    return message[start:end]


# --- substitution mechanics ------------------------------------------------


def test_substitution_only_expands_placeholders() -> None:
    template = '  before\n$profile\n$$literal\nvalue: {"name": "x"}\n  after  '

    result = prompts._substitute(template, "test", {"profile": "VALUE"})

    # placeholders expand; every other byte — braces, escaped `$`, whitespace — is literal
    assert result == '  before\nVALUE\n$literal\nvalue: {"name": "x"}\n  after  '


def test_an_unsupplied_placeholder_is_rejected() -> None:
    with pytest.raises(prompts.PromptCatalogError, match="model_calls.criteria"):
        prompts._substitute("$profile", "model_calls.criteria", {})


# --- catalogue validation --------------------------------------------------


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


# --- freshness: no resource is cached across composes ----------------------


def test_composition_reads_every_resource_fresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The catalogue, primer, and perspective files are re-read on every compose,
    so an edit to any of them reaches the next prompt without a restart."""
    from metis.wizard.application import config as config_module

    document = _document()
    (tmp_path / config_module.CONFIG_FILE).write_text(
        config_module._read_config_text(), encoding="utf-8"
    )
    (tmp_path / config_module.CAPABILITIES_FILE).write_text(
        config_module._read_capabilities_text(), encoding="utf-8"
    )
    prompts_path = tmp_path / prompts.PROMPTS_FILE
    prompts_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    )
    primer_path = tmp_path / prompts.PRIMER_FILE
    primer_path.write_text("FIRST PRIMER", encoding="utf-8")
    perspective_dir = tmp_path / prompts.PERSPECTIVES_DIR
    perspective_dir.mkdir()
    for name in ("end_user", "engineer", "compliance", "security"):
        (perspective_dir / f"{name}.md").write_text("FIRST LENS", encoding="utf-8")
    monkeypatch.setattr(prompts.resources, "files", lambda _package: tmp_path)

    first = prompts.clarify(research_assistant(), [], context=interview_context())

    document["model_calls"]["clarify"] += "\nEDITED TEMPLATE"
    prompts_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    )
    primer_path.write_text("SECOND PRIMER", encoding="utf-8")
    (perspective_dir / "end_user.md").write_text("SECOND LENS", encoding="utf-8")

    second = prompts.clarify(research_assistant(), [], context=interview_context())

    assert "FIRST PRIMER" in first.system
    assert "SECOND PRIMER" in second.system
    assert "FIRST LENS" in first.user
    assert "SECOND LENS" in second.user
    assert not first.user.endswith("EDITED TEMPLATE")
    assert second.user.endswith("EDITED TEMPLATE")


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


# --- composition contracts -------------------------------------------------


def test_configured_patch_rules_do_not_change_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["system"]["patch_rules"] = "The model may set measured."
    _install_document(monkeypatch, document)
    profile = research_assistant()

    assert "The model may set measured." in prompts.criteria(profile).system
    result = apply(
        profile,
        [
            Patch(
                op=PatchOp.SET,
                path="tasks[T-1].behaviours[EB-1].measured",
                value=False,
            )
        ],
    )

    assert result.applied == []
    assert len(result.rejected) == 1
    assert profile.behaviour("EB-1").measured is True  # type: ignore[union-attr]


def test_clarify_uses_one_shared_catalogue_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["model_calls"]["clarify"] += "\nSHARED CLARIFY MARKER"
    _install_document(monkeypatch, document)
    empty = ProductProfile(product=Product(name="", users="", description=""))

    prompt = prompts.clarify(empty, [], context=interview_context())

    assert prompt.name == "clarify"
    assert prompt.user.endswith("SHARED CLARIFY MARKER")


def test_clarify_progress_values_are_substituted_into_the_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["model_calls"]["clarify"] = (
        "<progress>$questions_asked/$question_cap/$questions_remaining</progress>"
    )
    _install_document(monkeypatch, document)

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

    assert prompts._clarify_progress(history) == (3, 5, 2)
    prompt = prompts.clarify(research_assistant(), history, context=interview_context())
    assert prompt.user == "<progress>3/5/2</progress>"

    at_cap = [
        *history,
        Turn(role="assistant", text="Question four?"),
        Turn(role="user", text="Answer four."),
        Turn(role="assistant", text="Question five?"),
        Turn(role="user", text="Answer five."),
    ]
    assert prompts._clarify_progress(at_cap) == (5, 5, 0)

    final_prompt = prompts.clarify(orca_handover(), at_cap, context=interview_context())
    assert final_prompt.user == "<progress>5/5/0</progress>"


# --- what each prompt is given ---------------------------------------------


@pytest.mark.parametrize(
    "compose",
    [
        lambda p: prompts.clarify(p, [], context=interview_context()),
        lambda p: prompts.behaviours(p, [], context=interview_context()),
        prompts.criteria,
        prompts.personas,
        prompts.scenarios,
    ],
)
def test_the_profile_is_serialized_into_every_prompt(
    compose: Callable[[ProductProfile], prompts.ModelPrompt],
) -> None:
    profile = orca_handover()
    serialized = json.dumps(profile.model_dump(mode="json"), indent=2)

    # the whole document, including newline-bearing detail, reaches the model verbatim
    prompt = compose(profile)
    assert serialized in _xml_content(prompt.user, "profile")


def test_clarify_evidence_is_injected_inside_xml_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["model_calls"]["clarify"] = "\n".join(
        (
            "<profile>$profile</profile>",
            "<transcript>$history</transcript>",
            "<perspective>$perspective</perspective>",
            "<capability_evidence>$capability_evidence</capability_evidence>",
        )
    )
    _install_document(monkeypatch, document)

    profile = orca_handover()
    history = [Turn(role="user", text="HISTORY_SENTINEL")]
    context = interview_context(
        perspective=Perspective.SECURITY,
        known_capability_ids=["tool_use"],
        confidence="high",
    )
    prompt = prompts.clarify(profile, history, context=context)

    assert json.dumps(profile.model_dump(mode="json"), indent=2) in _xml_content(
        prompt.user, "profile"
    )
    assert "user: HISTORY_SENTINEL" in _xml_content(prompt.user, "transcript")
    assert _perspective_text("security") in _xml_content(prompt.user, "perspective")
    capability_evidence = _xml_content(prompt.user, "capability_evidence")
    assert "tool_use" in capability_evidence
    assert context.capability_evidence.confidence.value in capability_evidence


def test_clarify_requires_capability_evidence_context() -> None:
    with pytest.raises(prompts.PromptCatalogError, match="capability evidence"):
        prompts.clarify(research_assistant(), [])


@pytest.mark.parametrize("builder", [prompts.clarify, prompts.behaviours])
def test_capability_evidence_is_injected_into_early_prompts(builder) -> None:
    context = interview_context(known_capability_ids=["tool_use"], confidence="high")

    prompt = builder(research_assistant(), [], context=context)

    assert "tool_use" in _xml_content(prompt.user, "capability_evidence")


def test_shared_context_reaches_every_model_call() -> None:
    context = interview_context()
    context.opening_description = "OPENING_SENTINEL"
    context.documents = [
        InterviewDocument(name="policy.md", text="DOCUMENT_SENTINEL"),
        InterviewDocument(name="sample.csv"),
    ]
    calls = [
        prompts.clarify(research_assistant(), [], context=context),
        prompts.behaviours(research_assistant(), [], context=context),
        prompts.criteria(research_assistant(), context=context),
        prompts.personas(research_assistant(), context=context),
        prompts.scenarios(research_assistant(), context=context),
        prompts.chat(research_assistant(), "criteria", "edit", None, context=context),
        prompts.suggest_criterion(research_assistant(), "EB-1", context=context),
    ]

    for index, prompt in enumerate(calls):
        assert prompts.arc_catalogue() in _xml_content(prompt.system, "arc_catalogue")
        assert (
            json.loads(_xml_content(prompt.system, "opening_description"))
            == "OPENING_SENTINEL"
        )
        assert json.loads(_xml_content(prompt.system, "interview_documents")) == [
            {"name": "policy.md", "text": "DOCUMENT_SENTINEL"},
            {"name": "sample.csv", "text": None},
        ]
        assert json.loads(_xml_content(prompt.system, "available_fixture_names")) == (
            ["policy.md", "sample.csv"] if index in {4, 5} else []
        )

    # capability evidence is a Clarify/Behaviours concern only, never a later call
    assert "tool_use" not in calls[2].user


def test_perspective_content_is_scoped_to_the_selected_lens() -> None:
    """Only the chosen perspective's body is embedded, and only in early prompts."""
    end_user_text = _perspective_text("end_user")
    security_text = _perspective_text("security")
    end_user = interview_context(perspective=Perspective.END_USER)
    security = interview_context(perspective=Perspective.SECURITY)

    for compose in (prompts.clarify, prompts.behaviours):
        chosen = compose(research_assistant(), [], context=end_user).user
        other = compose(research_assistant(), [], context=security).user
        assert end_user_text in _xml_content(chosen, "perspective")
        assert security_text not in _xml_content(chosen, "perspective")
        assert security_text in _xml_content(other, "perspective")
        assert end_user_text not in _xml_content(other, "perspective")

    # Later prompts carry the identity in the system message, but not the full lens.
    later = prompts.criteria(research_assistant(), context=security)
    assert _xml_content(later.system, "perspective").strip() == "security"
    assert end_user_text not in later.system
    assert security_text not in later.system
    assert end_user_text not in later.user
    assert security_text not in later.user
    assert "$perspective" not in later.system
    assert "$perspective" not in later.user


def test_perspective_identity_reaches_every_model_call() -> None:
    profile = research_assistant()
    context = interview_context(perspective=Perspective.SECURITY)
    calls = [
        prompts.clarify(profile, [], context=context),
        prompts.behaviours(profile, [], context=context),
        prompts.criteria(profile, context=context),
        prompts.personas(profile, context=context),
        prompts.scenarios(profile, context=context),
        prompts.chat(profile, "criteria", "edit", None, context=context),
        prompts.suggest_criterion(profile, "EB-1", context=context),
    ]

    for prompt in calls:
        assert _xml_content(prompt.system, "perspective").strip() == "security"


def test_system_and_chat_documents_use_xml_boundaries() -> None:
    profile = research_assistant()
    system = prompts.criteria(profile).system
    chat = prompts.chat(profile, "criteria", "USER_MESSAGE_SENTINEL", None).user

    assert prompts.primer() in _xml_content(system, "primer")
    assert prompts.arc_catalogue() in _xml_content(system, "arc_catalogue")
    assert "USER_MESSAGE_SENTINEL" in _xml_content(chat, "user_message")
