"""The model client: credentials, the retry loop, and the primer."""

import json
from dataclasses import dataclass, field

import pytest

from metis.wizard.adapters.llm.gateway import (
    API_KEY_VAR,
    ATTEMPTS,
    BASE_URL_VAR,
    CredentialsMissing,
    GatewayInterviewer,
    ModelOutputError,
    check_credentials,
)
from metis.wizard.application import prompts
from metis.wizard.contracts import ClarifyResult


@dataclass
class FakeCompletions:
    """Returns a scripted sequence of raw strings, recording what it was sent."""

    replies: list[str]
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]

        class Message:
            content = text

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]

        return Response()


@dataclass
class FakeClient:
    completions: FakeCompletions

    @property
    def chat(self):
        return self


def interviewer(replies: list[str]) -> tuple[GatewayInterviewer, FakeCompletions]:
    completions = FakeCompletions(replies=replies)
    return GatewayInterviewer(_client=FakeClient(completions=completions)), completions


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BASE_URL_VAR, "https://gateway.example")
    monkeypatch.setenv(API_KEY_VAR, "key")


# ── credentials ────────────────────────────────────────────────────────────


def test_missing_credentials_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fix is to export something, so the message says what."""
    monkeypatch.delenv(BASE_URL_VAR)
    monkeypatch.delenv(API_KEY_VAR)

    with pytest.raises(CredentialsMissing) as exc:
        check_credentials()

    assert BASE_URL_VAR in str(exc.value)
    assert API_KEY_VAR in str(exc.value)


def test_credentials_are_checked_before_any_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(API_KEY_VAR)

    with pytest.raises(CredentialsMissing):
        GatewayInterviewer()


# ── the retry loop ─────────────────────────────────────────────────────────


def test_a_first_attempt_miss_is_invisible() -> None:
    """A schema miss is common and recoverable; the user should never learn it happened."""
    good = ClarifyResult(done=False, question="What does it do?").model_dump_json()
    model, completions = interviewer(["{not json at all", good])

    result, recovered = model._ask("s", "u", ClarifyResult)

    assert result.question == "What does it do?"
    assert recovered  # a retry was needed, and the caller is told so
    assert len(completions.calls) == 2


def test_a_first_attempt_success_reports_no_recovery() -> None:
    """The flag is what lets a step keep the model's intro when nothing went wrong."""
    good = ClarifyResult(done=False, question="What does it do?").model_dump_json()
    model, _ = interviewer([good])

    _, recovered = model._ask("s", "u", ClarifyResult)

    assert not recovered


def test_the_validation_error_is_fed_back() -> None:
    """Retrying blind would be a worse use of the second attempt."""
    good = ClarifyResult(done=True).model_dump_json()
    model, completions = interviewer(["{}", good])

    model._ask("s", "u", ClarifyResult)

    retry_messages = completions.calls[1]["messages"]
    assert any("didn't validate" in m["content"] for m in retry_messages)


def test_a_recovered_step_drops_its_narrated_intro() -> None:
    """A retried turn tends to narrate the fix ("I've corrected the format"). That intro is
    implementation detail — it must never reach the user, so the gateway blanks it in code
    rather than trusting the model not to write it. The patches, the real output, survive."""
    from fixtures.profiles import research_assistant

    from metis.wizard.contracts import StepResult

    bad = "{not json at all"
    corrected = StepResult(
        message="I've corrected the criteria format to use proper objects.",
        patches=[],
    ).model_dump_json()
    model, completions = interviewer([bad, corrected])

    result = model._step("s", "u", research_assistant())

    assert (
        result.message == ""
    )  # the narration is gone; driver shows its neutral default
    assert len(completions.calls) == 2


def test_a_clean_step_keeps_the_model_intro() -> None:
    """First-attempt output is trusted — the justification the model writes is worth showing."""
    from fixtures.profiles import research_assistant

    from metis.wizard.contracts import StepResult

    clean = StepResult(
        message="These personas stress citation discipline and scope refusal.",
        patches=[],
    ).model_dump_json()
    model, _ = interviewer([clean])

    result = model._step("s", "u", research_assistant())

    assert (
        result.message == "These personas stress citation discipline and scope refusal."
    )


def test_three_failures_raise() -> None:
    model, completions = interviewer(["nonsense"])

    with pytest.raises(ModelOutputError):
        model._ask("s", "u", ClarifyResult)

    assert len(completions.calls) == ATTEMPTS


def test_raw_task_fields_are_rejected_before_profile_materialization() -> None:
    """The regression starts at provider JSON, before a typed Task can exist."""
    from fixtures.profiles import research_assistant

    invalid = json.dumps(
        {
            "message": "draft",
            "patches": [
                {
                    "op": "add",
                    "path": "tasks",
                    "value": {
                        "id": "MODEL-ID",
                        "description": "x",
                        "behaviour_refs": [],
                        "persona_refs": [],
                        "num_trials": 99,
                        "fixtures": ["secret.txt"],
                    },
                }
            ],
        }
    )
    valid = json.dumps(
        {
            "message": "draft",
            "patches": [
                {
                    "op": "add",
                    "path": "tasks",
                    "value": {
                        "description": "x",
                        "behaviour_refs": [],
                        "persona_refs": [],
                    },
                }
            ],
        }
    )
    model, completions = interviewer([invalid, valid])

    result = model._step("s", "u", research_assistant())

    assert result.patches[0].value.description == "x"
    assert len(completions.calls) == 2
    assert any(
        "didn't validate" in m["content"] for m in completions.calls[1]["messages"]
    )


def test_raw_nested_fields_are_rejected_and_corrected_atomically() -> None:
    from fixtures.profiles import research_assistant

    invalid = json.dumps(
        {
            "message": "draft",
            "patches": [
                {
                    "op": "add",
                    "path": "epics",
                    "value": {
                        "name": "Safety",
                        "behaviours": [
                            {
                                "statement": "refuses unsafe requests",
                                "priority": True,
                                "criteria": [{"metric_fqn": "forbidden"}],
                            }
                        ],
                    },
                }
            ],
        }
    )
    valid = json.dumps(
        {
            "message": "draft",
            "patches": [
                {
                    "op": "add",
                    "path": "epics",
                    "value": {
                        "name": "Safety",
                        "behaviours": [{"statement": "refuses unsafe requests"}],
                    },
                }
            ],
        }
    )
    model, completions = interviewer([invalid, valid])

    result = model._step("s", "u", research_assistant())

    assert result.patches[0].value.name == "Safety"
    assert len(completions.calls) == 2


def test_structured_output_is_requested_strictly() -> None:
    model, completions = interviewer([ClarifyResult(done=True).model_dump_json()])

    model._ask("s", "u", ClarifyResult)

    schema = completions.calls[0]["response_format"]
    assert schema["type"] == "json_schema"
    assert schema["json_schema"]["strict"] is True


def test_model_schema_has_no_persisted_or_runtime_fields() -> None:
    from metis.wizard.contracts import StepResult

    schema = StepResult.model_json_schema()

    def properties(node):
        if isinstance(node, dict):
            yield from node.get("properties", {}).keys()
            for value in node.values():
                yield from properties(value)
        elif isinstance(node, list):
            for value in node:
                yield from properties(value)

    names = set(properties(schema))
    assert not names & {
        "id",
        "priority",
        "metric_fqn",
        "metric_args",
        "fixtures",
        "num_trials",
        "origin",
        "options",
    }


def test_model_origin_is_not_part_of_provider_schema() -> None:
    """The provider cannot claim the runtime trust marker."""
    bad = json.dumps(
        {
            "message": "done",
            "patches": [
                {
                    "op": "set",
                    "path": "personas[cooperative-delegator].description",
                    "value": "x",
                    "origin": "wizard",
                }
            ],
        }
    )
    good = json.dumps({"message": "done", "patches": []})
    model, completions = interviewer([bad, good])
    from fixtures.profiles import research_assistant

    result = model._step("s", "u", research_assistant())

    assert result.patches == []
    assert len(completions.calls) == 2


def test_a_malformed_nested_patch_value_is_retried_atomically() -> None:
    """The patch envelope is valid, but its value is not an Epic.

    The model-facing schema and domain validation belong inside the same retry loop. The
    failed attempt must not apply its earlier product edit to the real profile.
    """
    from metis.wizard.contracts import EpicDraft, Product, ProductProfile

    profile = ProductProfile(product=Product(name="X", summary="", users=""))
    bad = json.dumps(
        {
            "message": "drafted",
            "patches": [
                {
                    "op": "set",
                    "path": "product.summary",
                    "value": "changed too early",
                },
                {
                    "op": "add",
                    "path": "epics",
                    "value": {
                        "name": "Routing",
                        "behaviours": [{"statement": "", "priority": True}],
                    },
                },
            ],
        }
    )
    empty = json.dumps(
        {
            "message": "drafted",
            "patches": [
                {
                    "op": "add",
                    "path": "epics",
                    "value": {"name": "Routing", "behaviours": []},
                }
            ],
        }
    )
    good = json.dumps(
        {
            "message": "drafted",
            "patches": [
                {"op": "set", "path": "product.summary", "value": "an orchestrator"},
                {
                    "op": "add",
                    "path": "epics",
                    "value": {
                        "name": "Routing",
                        "behaviours": [{"statement": "Routes to the right agent"}],
                    },
                },
            ],
        }
    )
    model, completions = interviewer([bad, empty, good])

    result = model.draft_behaviours(profile, [])

    assert len(completions.calls) == 3
    epic = result.patches[-1].value
    assert isinstance(epic, EpicDraft)
    assert epic.behaviours[0].statement
    assert profile.product.summary == ""
    assert profile.epics == []
    retry_messages = completions.calls[2]["messages"]
    assert any("priority" in message["content"] for message in retry_messages)
    assert any("behaviours" in message["content"] for message in retry_messages)


def test_a_duplicate_persona_description_is_retried() -> None:
    from fixtures.profiles import research_assistant

    from metis.wizard.contracts import StepResult

    profile = research_assistant()
    existing = profile.personas[0]
    duplicate = StepResult(
        message="added",
        patches=[
            {
                "op": "add",
                "path": "personas",
                "value": {"label": "duplicate", "description": existing.description},
            }
        ],  # type: ignore[list-item]
    ).model_dump_json()
    good = StepResult(message="updated", patches=[]).model_dump_json()
    model, completions = interviewer([duplicate, good])

    result = model.chat(profile, "personas", "Use these personas instead", None)

    assert result.patches == []
    assert len(completions.calls) == 2
    assert any(
        "duplicate one persona description" in message["content"]
        for message in completions.calls[1]["messages"]
    )


def test_chat_prompt_distinguishes_replacement_from_addition() -> None:
    from fixtures.profiles import research_assistant

    prompt = prompts.chat_user(
        research_assistant(),
        "personas",
        "These are the three personas I want",
        None,
    )

    assert "Replacement language is a replacement, not an addition" in prompt
    assert "Only append when the user clearly says to add" in prompt


# ── the primer ─────────────────────────────────────────────────────────────


def test_the_primer_is_in_the_system_prompt() -> None:
    system = prompts.system_prompt()

    assert prompts.primer() in system
    assert "never mention" in system.lower()


def test_the_primer_asks_about_machinery() -> None:
    """Its whole job is to make the interviewer curious about what it would not raise."""
    text = prompts.primer().lower()

    for concern in ["tool", "delegat", "memory", "recover", "retry"]:
        assert concern in text


def test_the_primer_is_not_a_checklist() -> None:
    """The moment it is cited or tracked, it has become one."""
    text = prompts.primer().lower()

    assert "not a checklist" in text
    assert "secondary to what they tell you" in text


def test_the_primer_warns_that_tasks_must_force_the_path() -> None:
    """The step that is easiest to miss and does the most work."""
    assert "untestable unless" in prompts.primer()


def test_changing_the_primer_file_changes_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is a file so it can be tuned without touching code or redeploying."""
    monkeypatch.setattr(prompts, "primer", lambda: "REPLACED PRIMER TEXT")

    assert "REPLACED PRIMER TEXT" in prompts.system_prompt()
    # monkeypatch restores the real function on teardown; its cache still holds the real
    # file's text, which is what every other test expects.


def test_every_step_prompt_hands_over_the_profile() -> None:
    """Steps build their prompts from the document, not the transcript."""
    from fixtures.profiles import research_assistant

    profile = research_assistant()

    for builder in (prompts.criteria_user, prompts.personas_user, prompts.tasks_user):
        assert "EB-1" in builder(profile)

    persona_prompt = prompts.personas_user(profile)
    assert "exactly these two fields" in persona_prompt
    assert all(f"`{field}`" in persona_prompt for field in ("id", "description"))


def test_the_patch_rules_forbid_the_protected_addresses() -> None:
    system = prompts.system_prompt()

    assert "priority" in system
    assert "metric_fqn" in system
