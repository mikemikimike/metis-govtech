"""The interview state machine: the clarify cap, the gates, and model failure."""

from dataclasses import dataclass

import pytest
from fixtures.profiles import research_assistant
from fixtures.scripted import ScriptedInterviewer

from metis.wizard.adapters.llm.gateway import ModelOutputError
from metis.wizard.application import SessionState, Turn
from metis.wizard.application.driver import StepDriver
from metis.wizard.application.interview import clarify_turn_cap
from metis.wizard.contracts import (
    ChatRequest,
    ChatResponse,
    ChoiceResponse,
    Product,
    ProductProfile,
    StepResult,
    WarningSource,
)
from metis.wizard.domain.permissions import SessionStep


def empty_state(step=SessionStep.CLARIFY, history=None) -> SessionState:
    return SessionState(
        id="s-1",
        profile=ProductProfile(product=Product(name="X", summary="", users="")),
        step=step,
        history=history or [],
    )


# ── the clarify cap ────────────────────────────────────────────────────────


@dataclass
class NeverDone(ScriptedInterviewer):
    """A model that always says it needs one more question."""

    def clarify(self, profile, history):
        self.calls.append("clarify")
        from metis.wizard.contracts import ClarifyResult

        return ClarifyResult(done=False, question="One more thing?")


def test_a_model_that_never_stops_is_stopped() -> None:
    """An interview that never ends is not recoverable; a thin first draft is."""
    driver = StepDriver(interviewer=NeverDone())
    history = [Turn(role="assistant", text=f"q{i}") for i in range(clarify_turn_cap())]
    state = empty_state(history=history)

    driver.compose(state)

    assert state.step is SessionStep.BEHAVIOURS  # drafted regardless


def test_below_the_cap_it_keeps_asking() -> None:
    driver = StepDriver(interviewer=NeverDone())
    state = empty_state(history=[Turn(role="assistant", text="q1")])

    request = driver.compose(state)

    assert request.prompt == "One more thing?"
    assert state.step is SessionStep.CLARIFY


def test_nothing_is_committed_during_clarify() -> None:
    """Answers live in history; the profile stays empty until behaviours are drafted."""
    driver = StepDriver(interviewer=ScriptedInterviewer(clarify_questions=5))
    state = empty_state()

    driver.compose(state)

    assert state.profile.tasks == []
    assert state.profile.scenarios == []


def test_the_configured_cap_is_positive() -> None:
    assert clarify_turn_cap() > 0


# ── the step header ────────────────────────────────────────────────────────


def _compose_at(step: SessionStep):
    """Compose the screen for one step over a fully-drafted profile, no model call needed."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = SessionState(id="s", profile=research_assistant(), step=step)
    return driver.compose(state)


def test_every_screen_reports_a_position_consistent_with_its_step() -> None:
    """The header is stamped once, from the step, so no screen can disagree with another.

    Positions are one-based and total six. Behaviours is the second of the six interview
    steps because clarify is the first, even though a chat rather than a screen composes it.
    """
    expected = {
        SessionStep.CLARIFY: ("Understanding your product", 1),
        SessionStep.BEHAVIOURS: ("Behaviours", 2),
        SessionStep.PRIORITISE: ("What to measure", 3),
        SessionStep.CRITERIA: ("Acceptance criteria", 4),
        SessionStep.PERSONAS: ("Personas", 5),
        SessionStep.SCENARIOS: ("Scenarios", 6),
    }

    for step, (title, position) in expected.items():
        request = _compose_at(step)
        assert request.title == title, step
        assert request.step == position, step
        assert request.steps == 6, step


def test_the_scenarios_screen_reports_six_of_six() -> None:
    request = _compose_at(SessionStep.SCENARIOS)

    assert (request.step, request.steps) == (6, 6)


def test_criteria_cards_carry_no_metric_annotation() -> None:
    request = _compose_at(SessionStep.CRITERIA)

    components = [component for card in request.cards for component in card.components]
    assert components
    assert all("note" not in component.model_dump() for component in components)
    assert all(
        "measured by:" not in component.text
        for component in components
        if hasattr(component, "text")
    )


def test_the_terminal_step_carries_no_header() -> None:
    """DONE is off the interview list, so a request stamped there draws no header."""
    from metis.wizard.application import screens
    from metis.wizard.contracts import ChatRequest

    request = ChatRequest(prompt="done")
    screens.stamp_step(request, SessionStep.DONE)

    assert (request.title, request.step, request.steps) == (None, None, None)


def test_a_mid_step_form_inherits_the_parent_steps_header() -> None:
    """Adding a persona mid-step keeps the personas header, not a new one."""
    from metis.wizard.contracts import ChoiceResponse

    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = SessionState(
        id="s", profile=research_assistant(), step=SessionStep.PERSONAS
    )
    screen = driver.compose(state)
    state.pending = screen

    add = next(o for o in screen.options if o.id.action == "add")
    driver.handle(state, screen, ChoiceResponse(selected=[str(add.id)]))

    form = state.pending
    assert form is not None
    assert (form.title, form.step, form.steps) == ("Personas", 5, 6)


def test_the_persona_add_form_keeps_the_description_and_generates_an_id() -> None:
    """One submission adds one persona in the original two-field shape."""
    from metis.wizard.contracts import ChoiceResponse, FormResponse

    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()
    before = len(profile.personas)
    state = SessionState(id="s", profile=profile, step=SessionStep.PERSONAS)
    screen = driver.compose(state)
    state.pending = screen

    add = next(o for o in screen.options if o.id.action == "add")
    driver.handle(state, screen, ChoiceResponse(selected=[str(add.id)]))
    form = state.pending
    assert form is not None
    assert [f.id for f in form.fields] == ["description"]

    driver.handle(
        state,
        form,
        FormResponse(values={"description": "Second-guesses each decision."}),
    )

    added = profile.personas[-1]
    assert len(profile.personas) == before + 1
    assert added.id == "P-1"
    assert added.description == "Second-guesses each decision."
    assert added.is_user_typed


# ── persona ids are the visible and referenced labels ───────────────────────


def test_a_persona_id_is_both_the_label_and_reference() -> None:
    """Cards, Run-as chips and scenario references use the same stable readable id."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()

    personas = driver.compose(
        SessionState(id="s", profile=profile, step=SessionStep.PERSONAS)
    )
    titles = {c.id: c.title for c in personas.cards}
    assert titles == {
        "cooperative-delegator": "cooperative-delegator",
        "impatient-executive": "impatient-executive",
    }

    from metis.wizard.contracts import CardOptionGroup

    scenarios = driver.compose(
        SessionState(id="s", profile=profile, step=SessionStep.SCENARIOS)
    )
    run_as = next(
        comp
        for card in scenarios.cards
        if card.id == "S-1"
        for comp in card.components
        if isinstance(comp, CardOptionGroup) and comp.label == "Run as"
    )
    chips = {opt.id.via: opt.label for opt in run_as.options}
    assert chips["cooperative-delegator"] == "cooperative-delegator"
    assert chips["impatient-executive"] == "impatient-executive"
    assert profile.scenario("S-1").persona_refs == list(chips)  # type: ignore[union-attr]


# ── the scenarios gates ─────────────────────────────────────────────────────


def _scenarios_screen(profile):
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = SessionState(id="s", profile=profile, step=SessionStep.SCENARIOS)
    return driver.compose(state)


def test_the_footer_matches_the_harness_expansion() -> None:
    profile = research_assistant()

    request = _scenarios_screen(profile)

    assert f"Total: {profile.run_count()} runs" == request.footer
    assert "scenarios" not in (request.footer or "")
    assert "pairs" not in (request.footer or "")

    cards = {card.id: card for card in request.cards}
    assert cards["S-1"].runs == 6
    assert cards["S-2"].runs == 3


def test_an_uncovered_behaviour_blocks_and_carries_its_fixes() -> None:
    profile = research_assistant()
    profile.scenarios = [
        t for t in profile.scenarios if t.id != "S-2"
    ]  # EB-3 now uncovered

    request = _scenarios_screen(profile)

    blocking = [w for w in request.warnings if w.blocking]
    assert blocking and "EB-3" in blocking[0].text
    assert [o.id.action for o in blocking[0].options][0] == "generate-scenario"
    assert any(o.id.action == "cover" for o in blocking[0].options)
    continue_option = next(o for o in request.options if o.id.action == "continue")
    assert not continue_option.enabled


def test_a_scenario_with_no_persona_blocks() -> None:
    """The schema declares persona_refs with minItems 1 — the engine would refuse the file."""
    profile = research_assistant()
    profile.scenario("S-1").persona_refs = []  # type: ignore[union-attr]

    request = _scenarios_screen(profile)

    assert any(w.blocking and "S-1" in w.text for w in request.warnings)


def test_run_count_is_zero_when_a_scenario_has_no_persona() -> None:
    profile = research_assistant()
    profile.scenario("S-1").persona_refs = []  # type: ignore[union-attr]

    request = _scenarios_screen(profile)
    card = next(card for card in request.cards if card.id == "S-1")

    assert card.runs == 0
    assert request.footer == "Total: 3 runs"


def test_run_count_uses_the_singular_for_one() -> None:
    profile = research_assistant()
    profile.scenario("S-1").persona_refs = []  # type: ignore[union-attr]
    profile.scenario("S-2").num_trials = 1  # type: ignore[union-attr]

    request = _scenarios_screen(profile)
    card = next(card for card in request.cards if card.id == "S-2")

    assert card.runs == 1
    assert request.footer == "Total: 1 run"


@pytest.mark.parametrize(
    ("refs", "blocks"),
    [
        (["EB-1"], False),  # a selected behaviour — fine
        ([], True),  # covers nothing at all
        (["EB-99"], True),  # only an unknown id
        (["EB-2"], True),  # EB-2 exists but is not ticked in the fixture
        (["EB-2", "EB-1"], False),  # one selected ref is enough
    ],
)
def test_a_scenario_must_cover_a_selected_behaviour(
    refs: list[str], blocks: bool
) -> None:
    """A scenario covers nothing measurable unless a currently selected behaviour is among its
    refs. Empty, unknown and unticked refs all fail the gate; one good ref clears it."""
    profile = research_assistant()
    profile.scenario("S-1").behaviour_refs = refs  # type: ignore[union-attr]

    request = _scenarios_screen(profile)

    flagged = any(
        w.blocking and "S-1 covers no selected" in w.text for w in request.warnings
    )
    assert flagged is blocks
    card = next(c for c in request.cards if c.id == "S-1")
    assert card.blocking is blocks


def test_the_coverage_gate_clears_itself() -> None:
    """Document warnings are recomputed every screen — covering a selected behaviour clears it."""
    profile = research_assistant()
    profile.scenario("S-1").behaviour_refs = []  # type: ignore[union-attr]
    assert any(w.blocking for w in _scenarios_screen(profile).warnings)

    profile.scenario("S-1").behaviour_refs = ["EB-1"]  # type: ignore[union-attr]

    request = _scenarios_screen(profile)
    assert not any("covers no selected" in w.text for w in request.warnings)


def test_the_gates_clear_themselves() -> None:
    """Document warnings are recomputed every screen — nothing carries a stale flag."""
    profile = research_assistant()
    profile.scenarios = [t for t in profile.scenarios if t.id != "S-2"]
    assert any(w.blocking for w in _scenarios_screen(profile).warnings)

    profile.scenario("S-1").behaviour_refs.append("EB-3")  # type: ignore[union-attr]

    request = _scenarios_screen(profile)
    assert not any(w.blocking for w in request.warnings)
    assert next(o for o in request.options if o.id.action == "continue").enabled


def test_scenario_card_fields_are_typed_and_separate_from_options() -> None:
    """Fields have stable identities without pretending to be selectable option chips."""
    from metis.wizard.application.driver import _all_options
    from metis.wizard.contracts import (
        CardNumberField,
        CardUploadField,
        editable_fields_of,
    )

    profile = research_assistant()
    request = _scenarios_screen(profile)
    card = next(c for c in request.cards if c.id == "S-2")

    number = next(c for c in card.components if isinstance(c, CardNumberField))
    upload = next(c for c in card.components if isinstance(c, CardUploadField))
    assert number.value == profile.scenario("S-2").num_trials  # type: ignore[union-attr]
    assert upload.value == ["policy.pdf"]

    keys = _all_options(request)
    assert str(number.id) not in keys and str(upload.id) not in keys
    fields = editable_fields_of(request)
    assert fields[str(number.id)] is number
    assert fields[str(upload.id)] is upload


def _scenario_edit_state():
    profile = research_assistant()
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = SessionState(id="s", profile=profile, step=SessionStep.SCENARIOS)
    return driver, state, driver.compose(state)


def test_a_trial_edit_recomposes_the_scenario_total() -> None:
    driver, state, request = _scenario_edit_state()

    driver.handle(state, request, ChoiceResponse(values={"trials:S-2": 7}))

    assert state.profile.scenario("S-2").num_trials == 7  # type: ignore[union-attr]
    refreshed = driver.compose(state)
    assert refreshed.footer == "Total: 13 runs"  # 2×3 + 1×7
    scenario_card = next(card for card in refreshed.cards if card.id == "S-2")
    assert next(c for c in scenario_card.components if c.type == "number").value == 7
    assert scenario_card.runs == 7


def test_fixture_edits_normalize_and_compile() -> None:
    driver, state, request = _scenario_edit_state()

    driver.handle(
        state,
        request,
        ChoiceResponse(values={"files:S-2": [" policy.pdf ", "faq.md", "policy.pdf"]}),
    )

    scenario = state.profile.scenario("S-2")
    assert scenario is not None and scenario.fixtures == ["policy.pdf", "faq.md"]

    from metis.wizard.application.compile import compile_experiment

    compiled = compile_experiment(state.profile, "edited")
    assert next(t for t in compiled["scenarios"] if t["id"] == "S-2")["fixtures"] == [
        "policy.pdf",
        "faq.md",
    ]

    refreshed = driver.compose(state)
    files = next(card for card in refreshed.cards if card.id == "S-2").components[-1]
    assert files.value == ["policy.pdf", "faq.md"]

    driver.handle(state, refreshed, ChoiceResponse(values={"files:S-2": ["faq.md"]}))
    assert state.profile.scenario("S-2").fixtures == ["faq.md"]  # type: ignore[union-attr]

    refreshed = driver.compose(state)
    driver.handle(state, refreshed, ChoiceResponse(values={"files:S-2": []}))
    assert state.profile.scenario("S-2").fixtures == []  # type: ignore[union-attr]
    assert "fixtures" not in next(
        t
        for t in compile_experiment(state.profile, "cleared")["scenarios"]
        if t["id"] == "S-2"
    )


@pytest.mark.parametrize(
    "response",
    [
        ChoiceResponse(values={"trials:S-2": 0}),
        ChoiceResponse(values={"trials:S-2": 21}),
        ChoiceResponse.model_construct(
            selected=[], values={"trials:S-2": ["not a number"]}
        ),
        ChoiceResponse(values={"files:S-2": ["../secret.txt"]}),
        ChoiceResponse(values={"files:S-2": ["/absolute.txt"]}),
        ChoiceResponse(values={"files:S-2": ["folder\\secret.txt"]}),
        ChoiceResponse(values={"files:S-2": [" "]}),
        ChoiceResponse(values={"trials:S-404": 4}),
        ChoiceResponse(values={"not-offered:S-2": 4}),
        ChoiceResponse(selected=["continue"], values={"trials:S-2": 4}),
        ChoiceResponse(values={"trials:S-2": 4, "files:S-2": []}),
    ],
)
def test_invalid_or_mixed_field_edits_do_not_mutate(response) -> None:
    driver, state, request = _scenario_edit_state()
    before = state.profile.model_copy(deep=True)

    driver.handle(state, request, response)

    assert state.profile == before
    refreshed = driver.compose(state)
    assert any(w.source is WarningSource.RUNTIME for w in refreshed.warnings)


def test_a_task_with_nothing_ticked_is_not_warned() -> None:
    """Leaving a task unticked is a legitimate choice, not a mistake to flag. The prioritise
    screen raises no warning for it, and Continue stays enabled."""
    profile = research_assistant()
    for behaviour in profile.behaviours():
        behaviour.priority = False
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = SessionState(id="s", profile=profile, step=SessionStep.PRIORITISE)

    request = driver.compose(state)

    assert not request.warnings
    assert next(o for o in request.options if o.id.action == "continue").enabled


# ── going back ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "destination", "expected_prompt"),
    [
        (
            SessionStep.PRIORITISE,
            SessionStep.BEHAVIOURS,
            "Review the behaviour draft.",
        ),
        (
            SessionStep.CRITERIA,
            SessionStep.PRIORITISE,
            "Which of these should we actually measure? "
            "I'll write acceptance criteria for the ones you pick.",
        ),
        (
            SessionStep.SCENARIOS,
            SessionStep.PERSONAS,
            "Review the personas.",
        ),
    ],
)
def test_every_visible_back_transition_restores_its_destination(
    source: SessionStep, destination: SessionStep, expected_prompt: str
) -> None:
    profile = research_assistant()
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    driver._step_messages = {
        SessionStep.BEHAVIOURS: "Review the behaviour draft.",
        SessionStep.CRITERIA: "Review the acceptance criteria.",
        SessionStep.PERSONAS: "Review the personas.",
        SessionStep.SCENARIOS: "Review the scenarios.",
    }
    state = SessionState(
        id="s",
        profile=profile,
        step=source,
        history=[Turn(role="user", text="Keep everything I already decided.")],
    )
    before_profile = profile.model_copy(deep=True)
    before_history = list(state.history)
    request = driver.compose(state)
    assert any(option.id.action == "back" for option in request.options)

    driver.handle(state, request, ChoiceResponse(selected=["back"]))
    destination_request = driver.compose(state)

    assert state.step is destination
    assert destination_request.prompt == expected_prompt
    assert state.profile == before_profile
    assert state.history == before_history
    assert interviewer.calls == []


def test_a_recomposed_screen_uses_a_neutral_message() -> None:
    profile = research_assistant()
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = SessionState(id="s", profile=profile, step=SessionStep.BEHAVIOURS)

    request = driver.compose(state)

    assert request.prompt == "Here's the current draft."


def test_going_back_regenerates_nothing_that_already_exists() -> None:
    """Continue generates only what is missing; existing criteria are left alone."""
    profile = research_assistant()
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    state = SessionState(id="s", profile=profile, step=SessionStep.PRIORITISE)
    before = profile.behaviour("EB-1").criteria[0].then  # type: ignore[union-attr]

    driver._advance(state)  # the Continue that generates

    assert "draft_criteria" not in interviewer.calls  # nothing was missing
    assert profile.behaviour("EB-1").criteria[0].then == before  # type: ignore[union-attr]


def test_unticking_then_continuing_generates_only_the_gap() -> None:
    profile = research_assistant()
    profile.behaviour("EB-1").criteria = []  # type: ignore[union-attr]
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    state = SessionState(id="s", profile=profile, step=SessionStep.PRIORITISE)

    driver._advance(state)

    assert "draft_criteria" in interviewer.calls
    assert profile.behaviour("EB-1").criteria  # filled
    assert len(profile.behaviour("EB-3").criteria) == 1  # type: ignore[union-attr]  # untouched


# ── total model failure ────────────────────────────────────────────────────


@dataclass
class BrokenInterviewer(ScriptedInterviewer):
    """Every attempt already failed inside the client."""

    def draft_personas(self, profile):
        raise ModelOutputError("three attempts, all malformed")


def test_a_total_failure_warns_and_loses_nothing() -> None:
    profile = research_assistant()
    profile.personas = []
    driver = StepDriver(interviewer=BrokenInterviewer())
    state = SessionState(id="s", profile=profile, step=SessionStep.PERSONAS)

    request = driver.compose(state)

    runtime = [w for w in request.warnings if w.source is WarningSource.RUNTIME]
    assert runtime and "nothing you've decided has been lost" in runtime[0].text.lower()
    assert not runtime[0].blocking
    assert state.profile.tasks  # the profile is intact
    assert state.step is SessionStep.PERSONAS  # and we did not advance past it


# ── responses that cost no model call ──────────────────────────────────────


def test_ticking_costs_no_model_call() -> None:
    profile = research_assistant()
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    state = SessionState(id="s", profile=profile, step=SessionStep.PRIORITISE)
    request = driver.compose(state)
    interviewer.calls.clear()

    driver.handle(state, request, ChoiceResponse(selected=["tick:EB-2"]))

    assert interviewer.calls == []
    assert profile.behaviour("EB-2").priority is True  # type: ignore[union-attr]


# ── a reworded criterion re-maps its metric, silently ───────────────────────

_AC1 = "tasks[T-1].behaviours[EB-1].criteria[AC-1-1].then"


@dataclass
class RewordingInterviewer(ScriptedInterviewer):
    """A chat that rewords one criterion, the way the model is told to when the user asks
    for a different metric — it never touches metric_fqn itself."""

    def chat(self, profile, step, text, target):
        self.calls.append("chat")
        from metis.wizard.contracts import Patch, PatchOp

        return StepResult(
            message="Reworded it.",
            patches=[
                Patch(op=PatchOp.SET, path=_AC1, value="it names the routing decision")
            ],
        )


class RecordingMatcher:
    """Records which criteria it was asked to (re)match, and stamps a marker so the effect
    is observable. Stands in for the embedding matcher, whose internals are tested elsewhere."""

    def __init__(self) -> None:
        self.matched: list[str] = []
        self.degraded = False

    def match(self, criterion) -> str:
        self.matched.append(criterion.id)
        return "metis.library.metrics.routing.RoutingAccuracyMetric"


def test_rewording_a_criterion_in_chat_rematches_only_it() -> None:
    """The other half of the metric rule: the model rewords, the matcher re-picks. Only the
    criterion whose text changed is rematched — untouched ones keep their metric and cost
    no call."""
    profile = research_assistant()
    matcher = RecordingMatcher()
    driver = StepDriver(interviewer=RewordingInterviewer(), matcher=matcher)
    state = SessionState(id="s", profile=profile, step=SessionStep.CRITERIA)

    driver.handle(
        state, ChatRequest(prompt="q", multiline=True), ChatResponse(text="use routing")
    )

    assert matcher.matched == ["AC-1-1"]  # only the reworded criterion
    assert (
        profile.behaviour("EB-1").criteria[0].metric_fqn  # type: ignore[union-attr]
        == "metis.library.metrics.routing.RoutingAccuracyMetric"
    )


# ── a scoped criteria chat stays on its own behaviour ────────────────────────

_EB1_THEN = "tasks[T-1].behaviours[EB-1].criteria[AC-1-1].then"
_EB2_THEN = "tasks[T-1].behaviours[EB-2].criteria[AC-2-1].then"


def _criterion_action(driver, state, action, label):
    """Return one EB-1 control while checking the user-facing workflow contract."""
    screen = driver.compose(state)
    state.pending = screen
    card = next(c for c in screen.cards if c.id == "EB-1")
    option = next(o for o in card.options if o.id.action == action)
    assert option.id.target == "EB-1"
    assert option.label == label
    return screen, option


@dataclass
class ReachesAcrossInterviewer(ScriptedInterviewer):
    """A chat that tries to edit the behaviour it was opened on *and* a different one.

    Stands for a model that took a scoped request too broadly. The in-scope reword should
    land; the sibling edit should be dropped, because the user opened this chat on one card.
    """

    def chat(self, profile, step, text, target):
        self.calls.append("chat")
        from metis.wizard.contracts import Patch, PatchOp

        return StepResult(
            message="Reworded both.",
            patches=[
                Patch(
                    op=PatchOp.SET,
                    path=_EB1_THEN,
                    value="it names the routing decision",
                ),
                Patch(
                    op=PatchOp.SET,
                    path=_EB2_THEN,
                    value="it should not have touched this",
                ),
            ],
        )


def test_a_scoped_criteria_chat_edits_only_its_own_behaviour() -> None:
    """A chat opened on EB-1's card carries EB-1 as its target. A patch the model aims at
    EB-2 is dropped and reported; only EB-1's reworded criterion is applied and rematched."""
    profile = research_assistant()
    matcher = RecordingMatcher()
    driver = StepDriver(interviewer=ReachesAcrossInterviewer(), matcher=matcher)
    state = SessionState(id="s", profile=profile, step=SessionStep.CRITERIA)

    before_eb2 = profile.behaviour("EB-2").criteria[0].then  # type: ignore[union-attr]
    screen, chat_option = _criterion_action(
        driver, state, "chat", "Chat about these criteria"
    )
    driver.handle(state, screen, ChoiceResponse(selected=[str(chat_option.id)]))
    chat = state.pending
    assert isinstance(chat, ChatRequest)
    assert chat.target == "EB-1"
    driver.handle(
        state,
        chat,
        ChatResponse(text="use routing"),
    )

    # EB-1's own criterion changed and was rematched; EB-2 was left exactly as it was.
    assert matcher.matched == ["AC-1-1"]
    assert (
        profile.behaviour("EB-1").criteria[0].then  # type: ignore[union-attr]
        == "it names the routing decision"
    )
    assert profile.behaviour("EB-2").criteria[0].then == before_eb2  # type: ignore[union-attr]
    assert any(w.source is WarningSource.RUNTIME for w in driver.pending_warnings)


# ── "Suggest one for me": one clean add, or nothing ──────────────────────────


def _suggest_on(profile, interviewer, matcher=None):
    """Drive the real "Suggest one for me" control on EB-1's card, the way the door would.

    Composes the criteria screen, finds the `another` option scoped to EB-1, and clicks it —
    so the behaviour id reaches the driver exactly as `OptionId.target`, not hand-fed."""
    from metis.wizard.contracts import ChoiceResponse

    driver = StepDriver(interviewer=interviewer, matcher=matcher)
    state = SessionState(id="s", profile=profile, step=SessionStep.CRITERIA)
    screen, another = _criterion_action(driver, state, "another", "Suggest one for me")
    driver.handle(state, screen, ChoiceResponse(selected=[str(another.id)]))
    return driver, state


def test_suggest_one_for_me_adds_exactly_one_criterion_and_matches_it() -> None:
    """The happy path: the model returns one add under EB-1, it is applied, and only the new
    criterion is matched — the two it already had keep their metrics and cost no call."""
    profile = research_assistant()
    matcher = RecordingMatcher()
    driver, _ = _suggest_on(profile, ScriptedInterviewer(), matcher)

    eb1 = profile.behaviour("EB-1")
    assert [c.id for c in eb1.criteria] == ["AC-1-1", "AC-1-2", "AC-1-3"]  # type: ignore[union-attr]
    assert matcher.matched == ["AC-1-3"]  # only the one just added
    assert not driver.pending_warnings


@dataclass
class SuggestsNothing(ScriptedInterviewer):
    def suggest_criterion(self, profile, behaviour_id):
        self.calls.append("suggest_criterion")
        return StepResult(message="Nothing to add.", patches=[])


@dataclass
class SuggestsTwo(ScriptedInterviewer):
    def suggest_criterion(self, profile, behaviour_id):
        self.calls.append("suggest_criterion")
        one = super().suggest_criterion(profile, behaviour_id)
        one.patches.append(one.patches[0].model_copy())  # a second add — not allowed
        return one


@dataclass
class SuggestsElsewhere(ScriptedInterviewer):
    def suggest_criterion(self, profile, behaviour_id):
        self.calls.append("suggest_criterion")
        from metis.wizard.contracts import Patch, PatchOp

        return StepResult(
            message="Added to the wrong behaviour.",
            patches=[
                Patch(
                    op=PatchOp.ADD,
                    path="tasks[T-1].behaviours[EB-2].criteria",
                    value={
                        "id": "AC-2-9",
                        "given": "g",
                        "when": "w",
                        "then": "t",
                    },
                )
            ],
        )


@pytest.mark.parametrize(
    "interviewer",
    [SuggestsNothing(), SuggestsTwo(), SuggestsElsewhere()],
    ids=["zero", "multiple", "out-of-target"],
)
def test_a_suggestion_that_is_not_one_clean_add_changes_nothing(interviewer) -> None:
    """Zero adds, more than one, or an add aimed at another behaviour are each refused whole:
    EB-1 is untouched, EB-2 is untouched, and the user is told nothing landed."""
    profile = research_assistant()
    before = profile.model_copy(deep=True)
    driver, _ = _suggest_on(profile, interviewer, RecordingMatcher())

    assert profile == before  # all-or-nothing: not a single patch applied
    assert any(w.source is WarningSource.RUNTIME for w in driver.pending_warnings)


# ── "Write one myself": each submission is one FORM criterion ────────────────


def _type_one(driver, state, values):
    """Click "Write one myself" on EB-1's card, then submit `values` into the form it raises.

    Goes through compose/handle both times so the behaviour id rides on the form as its
    target exactly as it would from the door, rather than being constructed by hand."""
    from metis.wizard.contracts import ChoiceResponse, FormRequest, FormResponse

    screen, type_it = _criterion_action(driver, state, "type", "Write one myself")
    driver.handle(state, screen, ChoiceResponse(selected=[str(type_it.id)]))

    form = state.pending
    assert isinstance(form, FormRequest)
    assert form.target == "EB-1"
    assert [f.id for f in form.fields] == ["given", "when", "then"]
    driver.handle(state, form, FormResponse(values=values))


def test_writing_two_criteria_by_hand_produces_two_distinct_ones() -> None:
    """Manual entry appends a FORM criterion under the card's behaviour, verbatim. A second
    submission gets its own scoped id rather than overwriting the first — the append-nothing
    bug is what this guards against."""
    profile = research_assistant()
    matcher = RecordingMatcher()
    driver = StepDriver(interviewer=ScriptedInterviewer(), matcher=matcher)
    state = SessionState(id="s", profile=profile, step=SessionStep.CRITERIA)

    _type_one(
        driver,
        state,
        {
            "given": "a long report",
            "when": "it is asked to summarise",
            "then": "it keeps every citation",
        },
    )
    _type_one(
        driver,
        state,
        {
            "given": "a follow-up",
            "when": "it answers again",
            "then": "it stays consistent",
        },
    )

    eb1 = profile.behaviour("EB-1")
    assert [c.id for c in eb1.criteria] == ["AC-1-1", "AC-1-2", "AC-1-3", "AC-1-4"]  # type: ignore[union-attr]
    fresh = eb1.criteria[-2:]  # type: ignore[union-attr]
    assert [c.given for c in fresh] == [
        "a long report",
        "a follow-up",
    ]  # verbatim, in order
    assert all(c.is_user_typed for c in fresh)  # stamped FORM — survives regeneration
    assert matcher.matched == ["AC-1-3", "AC-1-4"]  # each new one matched, once
