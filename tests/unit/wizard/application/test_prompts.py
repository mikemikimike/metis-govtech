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
from metis.wizard.contracts import Product, ProductProfile
from metis.wizard.contracts.interview_state import InterviewContext, Perspective, Turn
from metis.wizard.domain.applier import apply
from metis.wizard.domain.patch import Patch, PatchOp
from tests.fixtures.wizard.profiles import orca_handover, research_assistant


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


def test_substitution_preserves_every_unmodified_byte() -> None:
    template = "  before\n$profile\n$$literal\n  after  "

    result = prompts._substitute(template, "test", {"profile": "VALUE"})

    assert result == "  before\nVALUE\n$literal\n  after  "


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


def test_clarify_selects_distinct_product_and_machinery_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["model_calls"]["clarify_product"] += "\nPRODUCT PHASE MARKER"
    document["model_calls"]["clarify_machinery"] += "\nMACHINERY PHASE MARKER"
    _install_document(monkeypatch, document)
    empty = ProductProfile(product=Product(name="", users="", description=""))

    product = prompts.clarify(empty, [], "product")
    machinery = prompts.clarify(research_assistant(), [], "machinery")

    assert product.name == machinery.name == "clarify"
    assert product.user.endswith("PRODUCT PHASE MARKER")
    assert machinery.user.endswith("MACHINERY PHASE MARKER")


def test_clarify_and_behaviours_use_only_the_selected_perspective_content() -> None:
    end_user = InterviewContext(perspective=Perspective.END_USER)
    security = InterviewContext(perspective=Perspective.SECURITY)
    end_user_prompts = (
        prompts.clarify(research_assistant(), [], context=end_user),
        prompts.behaviours(research_assistant(), [], context=end_user),
    )
    security_prompts = (
        prompts.clarify(research_assistant(), [], context=security),
        prompts.behaviours(research_assistant(), [], context=security),
    )

    for prompt in end_user_prompts:
        assert "people who use the product" in prompt.user
        assert "instruction-data separation" not in prompt.user
    for prompt in security_prompts:
        assert "instruction-data separation" in prompt.user
        assert "people who use the product" not in prompt.user
    assert end_user_prompts[0].user != security_prompts[0].user


def test_later_prompts_do_not_receive_perspective_content() -> None:
    prompt = prompts.criteria(research_assistant())

    assert "instruction-data separation" not in prompt.user
    assert "$perspective" not in prompt.user


def test_a_perspective_edit_affects_the_next_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = Path(
        "packages/wizard/src/metis/wizard/application/perspectives/security.md"
    )
    perspective_dir = tmp_path / prompts.PERSPECTIVES_DIR
    perspective_dir.mkdir()
    perspective_path = perspective_dir / "security.md"
    perspective_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / prompts.PRIMER_FILE).write_text("primer", encoding="utf-8")
    for name in ("end_user", "engineer", "compliance"):
        (perspective_dir / f"{name}.md").write_text(
            "other perspective", encoding="utf-8"
        )
    monkeypatch.setattr(
        prompts.resources,
        "files",
        lambda package: (
            tmp_path
            if package == "metis.wizard.application"
            else Path("packages/wizard/src/metis/wizard")
        ),
    )
    first = prompts.clarify(
        research_assistant(),
        [],
        context=InterviewContext(perspective=Perspective.SECURITY),
    )
    perspective_path.write_text("EDITED SECURITY LENS", encoding="utf-8")
    second = prompts.clarify(
        research_assistant(),
        [],
        context=InterviewContext(perspective=Perspective.SECURITY),
    )

    assert "EDITED SECURITY LENS" not in first.user
    assert "EDITED SECURITY LENS" in second.user


@pytest.mark.parametrize("phase", ["product", "machinery"])
def test_clarify_is_told_to_merge_a_narrow_follow_up_without_losing_detail(
    phase: str,
) -> None:
    profile = orca_handover()
    history = [
        Turn(role="assistant", text="How does review work?"),
        Turn(
            role="user",
            text="A reviewer can request one revision from the slide maker.",
        ),
    ]

    prompt = prompts.clarify(profile, history, phase)  # type: ignore[arg-type]
    serialized = json.dumps(profile.model_dump(mode="json"), indent=2)

    assert serialized in prompt.user
    assert (
        "user: A reviewer can request one revision from the slide maker." in prompt.user
    )


def test_clarify_allows_an_explicit_correction_to_remove_detail() -> None:
    history = [
        Turn(
            role="user",
            text=(
                "Correction: Criteria Evaluator is not live. Remove it from the product detail."
            ),
        )
    ]

    prompt = prompts.clarify(orca_handover(), history, "machinery")

    assert "user: Correction: Criteria Evaluator is not live." in prompt.user


def test_rich_orca_detail_reaches_behaviour_and_scenario_prompts() -> None:
    profile = orca_handover()
    serialized = json.dumps(profile.model_dump(mode="json"), indent=2)

    downstream = (
        prompts.behaviours(profile, []),
        prompts.scenarios(profile),
    )

    for prompt in downstream:
        assert serialized in prompt.user


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

    assert prompts._clarify_position(history) == (4, 5)


def test_later_prompts_receive_product_detail_with_line_breaks() -> None:
    profile = research_assistant()
    profile.product.detail = "First line.\nSecond line."

    prompt = prompts.scenarios(profile)

    assert "First line.\\nSecond line." in prompt.user
