"""Interview state, persistence and resume.

Written before the implementation. The properties here are the ones the design promises out
loud — "closing the terminal at the personas step loses nothing", "resume is safe" — and they
are all about what survives a process ending at the wrong moment.
"""

import json
from pathlib import Path

import pytest
from fixtures.profiles import research_assistant
from fixtures.scripted import ScriptedInterviewer

from metis.wizard.application import (
    INTERVIEW_FORMAT_VERSION,
    Interview,
    InterviewState,
    InterviewVersionError,
    Turn,
)
from metis.wizard.contracts import (
    CardUploadField,
    ChatResponse,
    ChoiceRequest,
    ChoiceResponse,
    Option,
    OptionId,
    Product,
    ProductProfile,
    ScenarioCard,
    WizardRequestState,
)
from metis.wizard.domain.permissions import InterviewStep


def a_state(**overrides) -> InterviewState:
    # `pending` is a property over the request list rather than a field, so it is set after
    # construction. Tests keep saying `pending=` because that is what they mean.
    pending = overrides.pop("pending", None)
    defaults = dict(
        id="s-1",
        profile=research_assistant(),
        step=InterviewStep.PERSONAS,
        history=[Turn(role="user", text="hello"), Turn(role="assistant", text="hi")],
    )
    state = InterviewState(**{**defaults, **overrides})
    if pending is not None:
        state.pending = pending
    return state


def a_request() -> ChoiceRequest:
    return ChoiceRequest(
        prompt="Do these look right?",
        options=[Option(id=OptionId(action="accept"), label="Looks right")],
    )


def test_interview_fixture_preserves_its_wire_shape(
    fixtures_dir: Path,
) -> None:
    """A representative persisted interview keeps its wire shape and subtype information."""
    path = fixtures_dir / "interview_state_fixture.json"
    raw = json.loads(path.read_text())

    loaded = InterviewState.load(path)

    assert loaded.version == INTERVIEW_FORMAT_VERSION
    assert loaded.id == raw["id"] == "compat-v1"
    assert loaded.step is InterviewStep.PERSONAS
    assert [turn.model_dump(mode="json") for turn in loaded.history] == raw["history"]
    assert len(loaded.requests) == len(raw["requests"])
    assert loaded.requests[0].prompt == raw["requests"][0]["prompt"]
    assert isinstance(loaded.pending, ChoiceRequest)
    assert (
        loaded.profile.product.description == raw["profile"]["product"]["description"]
    )


def test_the_live_request_is_not_persisted_separately(tmp_path: Path) -> None:
    """One representation on disk, so the list and the live screen cannot disagree."""
    path = tmp_path / "interview_state.json"
    a_state(pending=a_request()).save(path)

    raw = json.loads(path.read_text())

    assert "pending" not in raw
    assert len(raw["requests"]) == 1
    assert raw["requests"][0]["state"] == "pending"


# ── the pending request rehydrates as its subclass ─────────────────────────


def test_pending_request_rehydrates_as_its_subclass(tmp_path: Path) -> None:
    """`Literal` discriminators exist so Pydantic rebuilds the right class, not the base."""
    state = a_state(pending=a_request())
    path = tmp_path / "interview_state.json"
    state.save(path)

    loaded = InterviewState.load(path)

    assert isinstance(loaded.pending, ChoiceRequest)
    assert loaded.pending.options[0].label == "Looks right"
    assert loaded.pending.options[0].id.action == "accept"


def test_old_comma_joined_file_field_rehydrates_as_a_list(tmp_path: Path) -> None:
    state = a_state(
        pending=ChoiceRequest(
            prompt="Edit scenarios",
            cards=[
                ScenarioCard(
                    id="S-2",
                    title="Retry",
                    trials=1,
                    components=[
                        CardUploadField(
                            label="Files",
                            id=OptionId(action="files", target="S-2"),
                            value="policy.pdf, faq.md",
                        )
                    ],
                )
            ],
        )
    )
    path = tmp_path / "legacy.json"
    state.save(path)

    loaded = InterviewState.load(path)
    field = loaded.pending.cards[0].components[0]  # type: ignore[union-attr]
    assert loaded.pending.cards[0].trials == 1  # type: ignore[union-attr]
    assert isinstance(field, CardUploadField)
    assert field.value == ["policy.pdf", "faq.md"]

    raw = json.loads(path.read_text())
    assert raw["requests"][0]["cards"][0]["components"][0]["value"] == [
        "policy.pdf",
        "faq.md",
    ]


def test_a_scenario_field_edit_survives_resume(tmp_path: Path) -> None:
    from fixtures.scripted import ScriptedInterviewer

    from metis.wizard.application.driver import StepDriver

    path = tmp_path / "interview_state.json"
    interview = Interview(
        a_state(step=InterviewStep.SCENARIOS),
        path=path,
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )
    interview.next()
    interview.respond(ChoiceResponse(values={"files:S-2": ["policy.pdf", "faq.md"]}))
    assert any("files:S-2" in turn.text for turn in interview.state.history)

    resumed = Interview.resume(
        path, driver=StepDriver(interviewer=ScriptedInterviewer())
    )
    request = resumed.next()
    assert resumed.state.profile.scenario("S-2").fixtures == [  # type: ignore[union-attr]
        "policy.pdf",
        "faq.md",
    ]
    assert request is not None
    card = next(card for card in request.cards if card.id == "S-2")  # type: ignore[union-attr]
    field = card.components[-1]
    assert isinstance(field, CardUploadField)
    assert field.value == ["policy.pdf", "faq.md"]


# ── persistence ────────────────────────────────────────────────────────────


def test_resuming_continues_from_the_pending_request(tmp_path: Path) -> None:
    """Closing the terminal mid-interview loses nothing, and re-pays no model call."""
    path = tmp_path / "interview_state.json"
    a_state(pending=a_request()).save(path)

    resumed = Interview.resume(path)

    assert resumed.state.step is InterviewStep.PERSONAS
    assert resumed.state.profile == research_assistant()
    assert isinstance(resumed.state.pending, ChoiceRequest)
    # .next() hands back what was already asked rather than composing a new screen
    assert resumed.next() is resumed.state.pending


# ── the conversation is a list, and answering is not the same as leaving ───


def _driven(step: InterviewStep) -> Interview:
    """An interview with a real driver, parked at one step."""
    from fixtures.scripted import ScriptedInterviewer

    from metis.wizard.application.driver import StepDriver

    return Interview(
        a_state(step=step, profile=research_assistant()),
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )


def test_a_tick_does_not_stack_a_second_copy_of_its_screen() -> None:
    """Toggling something leaves you on the screen you toggled it on.

    The regression this guards: resolving on every response, then recomposing, puts the same
    screen in the conversation twice — the first greyed out for no visible reason.
    """
    interview = _driven(InterviewStep.PRIORITISE)
    interview.next()
    before = interview.state.profile.behaviour("EB-2")
    assert before is not None and before.measured is False

    interview.respond(ChoiceResponse(selected=["tick:EB-2"]))
    interview.next()

    assert len(interview.state.requests) == 1
    assert interview.state.pending is not None  # still live, not a receipt
    after = interview.state.profile.behaviour("EB-2")
    assert after is not None and after.measured is True  # and the tick took


def test_a_cleared_behaviour_stays_clear_after_save_and_resume(tmp_path: Path) -> None:
    from metis.wizard.application.driver import StepDriver

    path = tmp_path / "interview_state.json"
    interview = Interview(
        a_state(step=InterviewStep.PRIORITISE),
        path=path,
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )
    interview.next()
    before = interview.state.profile.behaviour("EB-1")
    assert before is not None and before.measured is True

    interview.respond(ChoiceResponse(selected=["tick:EB-1"]))
    resumed = Interview.resume(
        path,
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )
    recomposed = resumed.next()

    behaviour = resumed.state.profile.behaviour("EB-1")
    assert behaviour is not None and behaviour.measured is False
    assert isinstance(recomposed, ChoiceRequest)
    card = next(card for card in recomposed.cards if card.id == "EB-1")
    assert card.selected is False
    assert card.options[0].selected is False


def test_continuing_resolves_the_screen_behind_it() -> None:
    interview = _driven(InterviewStep.PRIORITISE)
    interview.next()

    interview.respond(ChoiceResponse(selected=["continue"]))
    interview.next()

    assert len(interview.state.requests) == 2
    assert interview.state.requests[0].state is WizardRequestState.RESOLVED
    assert interview.state.requests[1].state is WizardRequestState.PENDING
    assert interview.state.step is InterviewStep.CRITERIA


def test_a_resolved_screen_records_what_was_chosen() -> None:
    """A receipt saying "Looks right · Chat about it · I'll add one" tells you nothing."""
    interview = _driven(InterviewStep.BEHAVIOURS)
    offered = interview.next()
    assert isinstance(offered, ChoiceRequest)
    assert [o.id.action for o in offered.options] == ["accept", "chat", "add", "add"]
    assert [o.id.target for o in offered.options if o.id.action == "add"] == [
        "T-1",
        "T-2",
    ]

    interview.respond(ChoiceResponse(selected=["accept"]))

    resolved = interview.state.requests[0]
    assert isinstance(resolved, ChoiceRequest)
    chosen = {o.id.action: o.selected for o in resolved.options}
    assert chosen["accept"] is True
    assert chosen["chat"] is not True
    assert chosen["add"] is not True
    assert not hasattr(resolved, "answer")


def test_resolved_typed_requests_carry_the_users_answer() -> None:
    """The typed-request contract records either answer shape on the request itself."""
    from metis.wizard.contracts import (
        ChatRequest,
        ChatResponse,
        FormField,
        FormRequest,
        FormResponse,
    )

    cases = [
        (
            ChatRequest(prompt="What does it do?"),
            ChatResponse(text="It answers research questions."),
            "It answers research questions.",
        ),
        (
            FormRequest(
                prompt="Add one yourself",
                fields=[
                    FormField(id="name", label="Name"),
                    FormField(id="description", label="Description"),
                ],
            ),
            FormResponse(
                values={"name": "Source citer", "description": "It cites its sources."}
            ),
            {"name": "Source citer", "description": "It cites its sources."},
        ),
    ]

    for request, response, expected in cases:
        interview = Interview(a_state(pending=request))

        interview.respond(response)

        resolved = interview.state.requests[0]
        assert isinstance(resolved, (ChatRequest, FormRequest))
        assert resolved.state is WizardRequestState.RESOLVED
        assert resolved.answer == expected


def test_a_targeted_follow_up_keeps_its_target_across_save_and_resume(
    tmp_path: Path,
) -> None:
    """A per-card action scopes its follow-up to one behaviour, and that scope must survive.

    `ChatRequest.target` / `FormRequest.target` are how the criteria screen's controls say
    *which* behaviour a chat or a manual criterion belongs to. If a save/resume round trip
    dropped it, a targeted edit would silently widen into a screen-wide one — the exact bug
    group 16 closes. Optional-with-default, so no format bump: the file simply carries a
    `target` key now.
    """
    from metis.wizard.contracts import ChatRequest, FormField, FormRequest

    chat = ChatRequest(
        prompt="What would you like to change about EB-2?", target="EB-2"
    )
    form = FormRequest(
        prompt="Write one yourself.",
        target="EB-2",
        fields=[FormField(id="given", label="Given")],
    )

    for index, request in enumerate((chat, form)):
        path = tmp_path / f"interview-{index}.json"
        a_state(pending=request).save(path)

        resumed = InterviewState.load(path)

        pending = resumed.pending
        assert isinstance(pending, (ChatRequest, FormRequest))
        assert type(pending) is type(request)
        assert pending.target == "EB-2"


def test_going_back_leaves_the_abandoned_screen_in_the_conversation() -> None:
    """Back sets the step. It does not rewrite what already happened."""
    interview = _driven(InterviewStep.SCENARIOS)
    interview.next()
    scenarios_before = len(interview.state.profile.scenarios)

    interview.back(InterviewStep.PERSONAS)
    interview.next()

    assert len(interview.state.requests) == 2
    assert interview.state.requests[0].state is WizardRequestState.RESOLVED
    assert interview.state.step is InterviewStep.PERSONAS
    assert (
        len(interview.state.profile.scenarios) == scenarios_before
    )  # nothing discarded


def test_a_version_six_interview_is_refused(tmp_path: Path) -> None:
    """The list replaced the single pending slot, so older files are not half-understood."""
    path = tmp_path / "interview_state.json"
    path.write_text('{"version": 6, "id": "s-1", "profile": {}, "pending": {}}')

    with pytest.raises(InterviewVersionError) as exc:
        InterviewState.load(path)

    message = str(exc.value)
    assert "6" in message
    assert str(INTERVIEW_FORMAT_VERSION) in message
    assert str(path) in message


def test_the_write_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash mid-write leaves the previous good interview, not a truncated file.

    That is the difference between losing one turn and losing the interview plus every model
    call already paid for.
    """
    import metis.wizard.contracts.interview_state as state_module

    path = tmp_path / "interview_state.json"
    a_state().save(path)
    good = path.read_text()

    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(state_module.os, "replace", explode)
    with pytest.raises(OSError):
        a_state(id="s-2").save(path)

    assert path.read_text() == good  # untouched
    assert list(tmp_path.iterdir()) == [path]  # and no temp file left behind


def test_saving_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "interview_state.json"
    a_state().save(path)
    a_state().save(path)

    assert [p.name for p in tmp_path.iterdir()] == ["interview_state.json"]


# ── the version check ──────────────────────────────────────────────────────


def test_an_older_interview_file_is_refused_by_name(tmp_path: Path) -> None:
    """Refused with both versions and the path — not a Pydantic traceback about a field."""
    path = tmp_path / "interview_state.json"
    path.write_text('{"version": 0, "id": "s-1", "profile": {}}')

    with pytest.raises(InterviewVersionError) as exc:
        InterviewState.load(path)

    message = str(exc.value)
    assert "0" in message
    assert str(INTERVIEW_FORMAT_VERSION) in message
    assert str(path) in message


def test_the_version_is_checked_before_anything_else_parses(tmp_path: Path) -> None:
    """The rest of the file is gibberish; the version check must still be what fires.

    Otherwise the promise that resume is safe is kept only by luck — a changed model would
    surface as a validation error about a field nobody has heard of.
    """
    path = tmp_path / "interview_state.json"
    path.write_text('{"version": 0, "profile": {"nonsense": true}, "step": "invented"}')

    with pytest.raises(InterviewVersionError):
        InterviewState.load(path)


def test_a_current_version_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "interview_state.json"
    a_state().save(path)

    assert InterviewState.load(path).version == INTERVIEW_FORMAT_VERSION


def test_a_request_without_step_metadata_still_loads(tmp_path: Path) -> None:
    """The header fields are optional, so an interview saved before they existed still resumes.

    `title`, `step` and `steps` were added to `WizardRequest` after the original request shape. A
    `interview_state.json` whose stored request predates them has no such keys; because the fields
    default to `None`, it must validate and simply render without a header rather than being
    rejected for missing metadata. The interview version may still advance for a separate wire
    contract change, as it does for the scenario-card discriminator in this change.
    """
    path = tmp_path / "interview_state.json"
    path.write_text(
        json.dumps(
            {
                "version": INTERVIEW_FORMAT_VERSION,
                "id": "pre-metadata",
                "profile": research_assistant().model_dump(mode="json"),
                "step": "personas",
                "history": [],
                "requests": [
                    {
                        "type": "choice",
                        "prompt": "Do these look right?",
                        "state": "pending",
                        "options": [
                            {"id": {"action": "accept"}, "label": "Looks right"}
                        ],
                    }
                ],
            }
        )
    )

    loaded = InterviewState.load(path)

    assert isinstance(loaded.pending, ChoiceRequest)
    assert loaded.pending.title is None
    assert loaded.pending.step is None
    assert loaded.pending.steps is None


# ── going back ─────────────────────────────────────────────────────────────


def test_back_sets_the_step_and_nothing_else() -> None:
    """Not a mechanism — nothing is truncated and nothing is replayed."""
    interview = Interview(a_state(step=InterviewStep.SCENARIOS))
    before = interview.state.profile.model_copy(deep=True)
    history_length = len(interview.state.history)

    interview.back(InterviewStep.PRIORITISE)

    assert interview.state.step is InterviewStep.PRIORITISE
    assert (
        interview.state.profile == before
    )  # every scenario, persona and criterion intact
    assert len(interview.state.history) == history_length


# ── the corridor ───────────────────────────────────────────────────────────


def test_next_returns_none_exactly_when_finished() -> None:
    interview = Interview(a_state(step=InterviewStep.DONE))

    assert interview.next() is None


def test_respond_records_the_turn_and_saves(tmp_path: Path) -> None:
    from metis.wizard.contracts import ChatRequest, ChatResponse

    path = tmp_path / "interview_state.json"
    interview = Interview(
        a_state(pending=ChatRequest(prompt="What does it do?")), path=path
    )

    interview.respond(ChatResponse(text="It answers research questions."))

    assert interview.state.pending is None
    assert interview.state.history[-1].text == "It answers research questions."
    assert path.exists()
    assert InterviewState.load(path).history[-1].role == "user"


def test_a_fresh_interview_starts_at_clarify() -> None:
    interview = Interview.start(
        ProductProfile(product=Product(name="X", description="", users=""))
    )

    assert interview.state.step is InterviewStep.CLARIFY
    assert interview.state.id


def test_product_writes_are_persisted_before_the_next_question(tmp_path: Path) -> None:
    from metis.wizard.application.driver import StepDriver

    interview = Interview.start(
        ProductProfile(product=Product(name="", description="", users="")),
        path=tmp_path / "interview_state.json",
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )

    opening = interview.next()
    assert opening is not None
    interview.respond(ChatResponse(text="It answers research questions."))
    question = interview.next()

    saved = InterviewState.load(tmp_path / "interview_state.json")
    assert saved.history[0].role == "assistant"
    assert saved.history[0].text == opening.prompt
    assert saved.profile.product.name == "Research assistant"
    assert saved.profile.product.detail
    assert question is not None


def test_product_line_breaks_survive_persistence_and_prompt_composition(
    tmp_path: Path,
) -> None:
    from metis.wizard.application import prompts

    profile = research_assistant()
    profile.product.detail = "First line.\nSecond line."
    path = tmp_path / "interview_state.json"
    InterviewState(id="s", profile=profile).save(path)

    loaded = InterviewState.load(path)
    prompt = prompts.scenarios(loaded.profile)

    assert loaded.profile.product.detail == "First line.\nSecond line."
    assert "First line.\\nSecond line." in prompt.user
