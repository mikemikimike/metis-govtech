"""Session state, persistence and resume.

Written before the implementation. The properties here are the ones the design promises out
loud — "closing the terminal at the personas step loses nothing", "resume is safe" — and they
are all about what survives a process ending at the wrong moment.
"""

import json
from pathlib import Path

import pytest
from fixtures.profiles import research_assistant

from metis.wizard.application import (
    SESSION_FORMAT_VERSION,
    Session,
    SessionState,
    SessionVersionError,
    Turn,
)
from metis.wizard.contracts import (
    CardUploadField,
    ChoiceRequest,
    ChoiceResponse,
    Option,
    OptionId,
    Product,
    ProductProfile,
    ScenarioCard,
    WizardRequestState,
)
from metis.wizard.domain.permissions import SessionStep


def a_state(**overrides) -> SessionState:
    # `pending` is a property over the request list rather than a field, so it is set after
    # construction. Tests keep saying `pending=` because that is what they mean.
    pending = overrides.pop("pending", None)
    defaults = dict(
        id="s-1",
        profile=research_assistant(),
        step=SessionStep.PERSONAS,
        history=[Turn(role="user", text="hello"), Turn(role="assistant", text="hi")],
    )
    state = SessionState(**{**defaults, **overrides})
    if pending is not None:
        state.pending = pending
    return state


def a_request() -> ChoiceRequest:
    return ChoiceRequest(
        prompt="Do these look right?",
        options=[Option(id=OptionId(action="accept"), label="Looks right")],
    )


def test_session_fixture_preserves_its_wire_shape(
    fixtures_dir: Path,
) -> None:
    """A representative persisted session keeps its wire shape and subtype information."""
    path = fixtures_dir / "session_fixture.json"
    raw = json.loads(path.read_text())

    loaded = SessionState.load(path)

    assert loaded.version == SESSION_FORMAT_VERSION
    assert loaded.id == raw["id"] == "compat-v1"
    assert loaded.step is SessionStep.PERSONAS
    assert [turn.model_dump(mode="json") for turn in loaded.history] == raw["history"]
    assert [r.model_dump(mode="json") for r in loaded.requests] == raw["requests"]
    assert isinstance(loaded.pending, ChoiceRequest)
    assert loaded.profile.model_dump(mode="json") == raw["profile"]


def test_the_live_request_is_not_persisted_separately(tmp_path: Path) -> None:
    """One representation on disk, so the list and the live screen cannot disagree."""
    path = tmp_path / "session.json"
    a_state(pending=a_request()).save(path)

    raw = json.loads(path.read_text())

    assert "pending" not in raw
    assert len(raw["requests"]) == 1
    assert raw["requests"][0]["state"] == "pending"


# ── the pending request rehydrates as its subclass ─────────────────────────


def test_pending_request_rehydrates_as_its_subclass(tmp_path: Path) -> None:
    """`Literal` discriminators exist so Pydantic rebuilds the right class, not the base."""
    state = a_state(pending=a_request())
    path = tmp_path / "session.json"
    state.save(path)

    loaded = SessionState.load(path)

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
                    runs=1,
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

    loaded = SessionState.load(path)
    field = loaded.pending.cards[0].components[0]  # type: ignore[union-attr]
    assert loaded.pending.cards[0].runs == 1  # type: ignore[union-attr]
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

    path = tmp_path / "session.json"
    session = Session(
        a_state(step=SessionStep.SCENARIOS),
        path=path,
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )
    session.next()
    session.respond(ChoiceResponse(values={"files:S-2": ["policy.pdf", "faq.md"]}))
    assert any("files:S-2" in turn.text for turn in session.state.history)

    resumed = Session.resume(path, driver=StepDriver(interviewer=ScriptedInterviewer()))
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
    path = tmp_path / "session.json"
    a_state(pending=a_request()).save(path)

    resumed = Session.resume(path)

    assert resumed.state.step is SessionStep.PERSONAS
    assert resumed.state.profile == research_assistant()
    assert isinstance(resumed.state.pending, ChoiceRequest)
    # .next() hands back what was already asked rather than composing a new screen
    assert resumed.next() is resumed.state.pending


# ── the conversation is a list, and answering is not the same as leaving ───


def _driven(step: SessionStep) -> Session:
    """A session with a real driver, parked at one step."""
    from fixtures.scripted import ScriptedInterviewer

    from metis.wizard.application.driver import StepDriver

    return Session(
        a_state(step=step, profile=research_assistant()),
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )


def test_a_tick_does_not_stack_a_second_copy_of_its_screen() -> None:
    """Toggling something leaves you on the screen you toggled it on.

    The regression this guards: resolving on every response, then recomposing, puts the same
    screen in the conversation twice — the first greyed out for no visible reason.
    """
    session = _driven(SessionStep.PRIORITISE)
    session.next()
    before = session.state.profile.behaviour("EB-2")
    assert before is not None and before.priority is False

    session.respond(ChoiceResponse(selected=["tick:EB-2"]))
    session.next()

    assert len(session.state.requests) == 1
    assert session.state.pending is not None  # still live, not a receipt
    after = session.state.profile.behaviour("EB-2")
    assert after is not None and after.priority is True  # and the tick took


def test_continuing_resolves_the_screen_behind_it() -> None:
    session = _driven(SessionStep.PRIORITISE)
    session.next()

    session.respond(ChoiceResponse(selected=["continue"]))
    session.next()

    assert len(session.state.requests) == 2
    assert session.state.requests[0].state is WizardRequestState.RESOLVED
    assert session.state.requests[1].state is WizardRequestState.PENDING
    assert session.state.step is SessionStep.CRITERIA


def test_a_resolved_screen_records_what_was_chosen() -> None:
    """A receipt saying "Looks right · Chat about it · I'll add one" tells you nothing."""
    session = _driven(SessionStep.BEHAVIOURS)
    offered = session.next()
    assert isinstance(offered, ChoiceRequest)
    assert [o.id.action for o in offered.options] == ["accept", "chat", "add"]

    session.respond(ChoiceResponse(selected=["accept"]))

    resolved = session.state.requests[0]
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
                fields=[FormField(id="statement", label="Statement")],
            ),
            FormResponse(values={"statement": "It cites its sources."}),
            {"statement": "It cites its sources."},
        ),
    ]

    for request, response, expected in cases:
        session = Session(a_state(pending=request))

        session.respond(response)

        resolved = session.state.requests[0]
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
        path = tmp_path / f"session-{index}.json"
        a_state(pending=request).save(path)

        resumed = SessionState.load(path)

        pending = resumed.pending
        assert isinstance(pending, (ChatRequest, FormRequest))
        assert type(pending) is type(request)
        assert pending.target == "EB-2"


def test_going_back_leaves_the_abandoned_screen_in_the_conversation() -> None:
    """Back sets the step. It does not rewrite what already happened."""
    session = _driven(SessionStep.SCENARIOS)
    session.next()
    scenarios_before = len(session.state.profile.scenarios)

    session.back(SessionStep.PERSONAS)
    session.next()

    assert len(session.state.requests) == 2
    assert session.state.requests[0].state is WizardRequestState.RESOLVED
    assert session.state.step is SessionStep.PERSONAS
    assert len(session.state.profile.scenarios) == scenarios_before  # nothing discarded


def test_a_version_one_session_is_refused(tmp_path: Path) -> None:
    """The list replaced the single pending slot, so older files are not half-understood."""
    path = tmp_path / "session.json"
    path.write_text('{"version": 1, "id": "s-1", "profile": {}, "pending": {}}')

    with pytest.raises(SessionVersionError) as exc:
        SessionState.load(path)

    message = str(exc.value)
    assert "1" in message
    assert str(SESSION_FORMAT_VERSION) in message
    assert str(path) in message


def test_the_write_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash mid-write leaves the previous good session, not a truncated file.

    That is the difference between losing one turn and losing the interview plus every model
    call already paid for.
    """
    import metis.wizard.contracts.session_state as state_module

    path = tmp_path / "session.json"
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
    path = tmp_path / "session.json"
    a_state().save(path)
    a_state().save(path)

    assert [p.name for p in tmp_path.iterdir()] == ["session.json"]


# ── the version check ──────────────────────────────────────────────────────


def test_an_older_session_file_is_refused_by_name(tmp_path: Path) -> None:
    """Refused with both versions and the path — not a Pydantic traceback about a field."""
    path = tmp_path / "session.json"
    path.write_text('{"version": 0, "id": "s-1", "profile": {}}')

    with pytest.raises(SessionVersionError) as exc:
        SessionState.load(path)

    message = str(exc.value)
    assert "0" in message
    assert str(SESSION_FORMAT_VERSION) in message
    assert str(path) in message


def test_the_version_is_checked_before_anything_else_parses(tmp_path: Path) -> None:
    """The rest of the file is gibberish; the version check must still be what fires.

    Otherwise the promise that resume is safe is kept only by luck — a changed model would
    surface as a validation error about a field nobody has heard of.
    """
    path = tmp_path / "session.json"
    path.write_text('{"version": 0, "profile": {"nonsense": true}, "step": "invented"}')

    with pytest.raises(SessionVersionError):
        SessionState.load(path)


def test_a_current_version_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    a_state().save(path)

    assert SessionState.load(path).version == SESSION_FORMAT_VERSION


def test_a_request_without_step_metadata_still_loads(tmp_path: Path) -> None:
    """The header fields are optional, so a session saved before they existed still resumes.

    `title`, `step` and `steps` were added to `WizardRequest` after the original request shape. A
    `session.json` whose stored request predates them has no such keys; because the fields
    default to `None`, it must validate and simply render without a header rather than being
    rejected for missing metadata. The session version may still advance for a separate wire
    contract change, as it does for the scenario-card discriminator in this change.
    """
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "version": SESSION_FORMAT_VERSION,
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

    loaded = SessionState.load(path)

    assert isinstance(loaded.pending, ChoiceRequest)
    assert loaded.pending.title is None
    assert loaded.pending.step is None
    assert loaded.pending.steps is None


# ── going back ─────────────────────────────────────────────────────────────


def test_back_sets_the_step_and_nothing_else() -> None:
    """Not a mechanism — nothing is truncated and nothing is replayed."""
    session = Session(a_state(step=SessionStep.SCENARIOS))
    before = session.state.profile.model_copy(deep=True)
    history_length = len(session.state.history)

    session.back(SessionStep.PRIORITISE)

    assert session.state.step is SessionStep.PRIORITISE
    assert (
        session.state.profile == before
    )  # every scenario, persona and criterion intact
    assert len(session.state.history) == history_length


# ── the corridor ───────────────────────────────────────────────────────────


def test_next_returns_none_exactly_when_finished() -> None:
    session = Session(a_state(step=SessionStep.DONE))

    assert session.next() is None


def test_respond_records_the_turn_and_saves(tmp_path: Path) -> None:
    from metis.wizard.contracts import ChatRequest, ChatResponse

    path = tmp_path / "session.json"
    session = Session(
        a_state(pending=ChatRequest(prompt="What does it do?")), path=path
    )

    session.respond(ChatResponse(text="It answers research questions."))

    assert session.state.pending is None
    assert session.state.history[-1].text == "It answers research questions."
    assert path.exists()
    assert SessionState.load(path).history[-1].role == "user"


def test_a_fresh_session_starts_at_clarify() -> None:
    session = Session.start(
        ProductProfile(product=Product(name="X", summary="", users=""))
    )

    assert session.state.step is SessionStep.CLARIFY
    assert session.state.id
