"""The interview state machine: the clarify cap, the gates, and model failure."""

from dataclasses import dataclass

import pytest
from fixtures.profiles import research_assistant
from fixtures.scripted import ScriptedInterviewer

from metis.wizard.adapters.llm.gateway import ModelOutputError
from metis.wizard.application import InterviewState, Turn
from metis.wizard.application.config import clarify_turn_cap, opening_question
from metis.wizard.application.driver import StepDriver
from metis.wizard.contracts import (
    ChatRequest,
    ChatResponse,
    ChoiceResponse,
    Product,
    ProductProfile,
    StepResult,
    WarningSource,
)
from metis.wizard.domain.permissions import InterviewStep
from metis.wizard.domain.profile import collect_profile_ids


def empty_state(step=InterviewStep.CLARIFY, history=None) -> InterviewState:
    return InterviewState(
        id="s-1",
        profile=ProductProfile(product=Product(name="X", description="", users="")),
        step=step,
        history=history or [],
    )


# ── the clarify cap ────────────────────────────────────────────────────────


@dataclass
class NeverDone(ScriptedInterviewer):
    """A model that always says it needs one more question."""

    def clarify(self, profile, history, phase="product"):
        self.calls.append("clarify")
        from metis.wizard.contracts import ClarifyResult

        return ClarifyResult(message="One more thing?", done=False)


def after_opening(*model_questions: str) -> list[Turn]:
    return [
        Turn(role="assistant", text=opening_question()),
        Turn(role="user", text="It answers research questions."),
        *(Turn(role="assistant", text=q) for q in model_questions),
    ]


def test_the_opening_question_costs_no_model_call() -> None:
    interviewer = NeverDone()
    driver = StepDriver(interviewer=interviewer)

    request = driver.compose(empty_state())

    assert isinstance(request, ChatRequest)
    assert request.prompt == opening_question()
    assert interviewer.calls == []


def test_a_model_that_never_stops_is_stopped() -> None:
    """An interview that never ends is not recoverable; a thin first draft is."""
    driver = StepDriver(interviewer=NeverDone())
    history = after_opening(*(f"q{i}" for i in range(clarify_turn_cap())))
    state = empty_state(history=history)

    driver.compose(state)

    assert state.step is InterviewStep.BEHAVIOURS  # drafted regardless


def test_below_the_cap_it_keeps_asking() -> None:
    driver = StepDriver(interviewer=NeverDone())
    state = empty_state(history=after_opening("q1"))

    request = driver.compose(state)

    assert request.prompt == "One more thing?"
    assert state.step is InterviewStep.CLARIFY


def test_clarify_commits_product_but_not_behaviours() -> None:
    """Clarify writes the product before the next question, but never drafts behaviours."""
    driver = StepDriver(interviewer=ScriptedInterviewer(clarify_questions=5))
    state = empty_state(history=after_opening())

    request = driver.compose(state)

    assert request.prompt
    assert state.profile.product.name == "Research assistant"
    assert state.profile.product.users == "Policy analysts"
    assert state.profile.product.description
    assert state.profile.product.detail
    assert state.profile.tasks == []
    assert state.profile.scenarios == []


def test_a_thin_answer_leaves_the_product_gate_closed() -> None:
    @dataclass
    class ThinInterviewer(ScriptedInterviewer):
        def clarify(self, profile, history, phase="product"):
            from metis.wizard.contracts import ClarifyResult

            return ClarifyResult(message="Tell me a little more.", done=False)

    state = empty_state(history=after_opening())
    driver = StepDriver(interviewer=ThinInterviewer())

    request = driver.compose(state)

    assert request.prompt == "Tell me a little more."
    assert state.profile.product.description == ""
    assert state.profile.product.users == ""
    assert state.step is InterviewStep.CLARIFY


def test_clarify_rejects_a_non_product_patch() -> None:
    @dataclass
    class WritesABehaviour(NeverDone):
        def clarify(self, profile, history, phase="product"):
            from metis.wizard.contracts import ClarifyResult

            return ClarifyResult(
                message="One more thing?",
                done=False,
                patches=[
                    {
                        "op": "set",
                        "path": "tasks[T-1].name",
                        "value": "Not during clarify",
                    }
                ],
            )

    state = empty_state(history=after_opening())
    driver = StepDriver(interviewer=WritesABehaviour())

    driver.compose(state)

    assert state.profile.tasks == []


def test_a_later_product_edit_does_not_move_the_step() -> None:
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = empty_state(step=InterviewStep.CRITERIA)

    driver._run(
        state,
        StepResult(
            message="",
            patches=[
                {
                    "op": "set",
                    "path": "product.description",
                    "value": "A corrected description",
                }
            ],
        ),
    )

    assert state.profile.product.description == "A corrected description"
    assert state.step is InterviewStep.CRITERIA


def test_the_configured_cap_is_positive() -> None:
    assert clarify_turn_cap() > 0


# ── the step header ────────────────────────────────────────────────────────


def _compose_at(step: InterviewStep):
    """Compose the screen for one step over a fully-drafted profile, no model call needed."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = InterviewState(id="s", profile=research_assistant(), step=step)
    return driver.compose(state)


def test_every_screen_reports_a_position_consistent_with_its_step() -> None:
    """The header is stamped once, from the step, so no screen can disagree with another.

    Positions are one-based and total five. Behaviours is the second of the five interview
    steps because clarify is the first, even though a chat rather than a screen composes it.
    """
    expected = {
        InterviewStep.CLARIFY: ("Understanding your product", 1),
        InterviewStep.BEHAVIOURS: ("Behaviours", 2),
        InterviewStep.CRITERIA: ("Acceptance criteria", 3),
        InterviewStep.PERSONAS: ("Personas", 4),
        InterviewStep.SCENARIOS: ("Scenarios", 5),
    }

    for step, (title, position) in expected.items():
        request = _compose_at(step)
        assert request.title == title, step
        assert request.step == position, step
        assert request.steps == 5, step


def test_the_scenarios_screen_reports_five_of_five() -> None:
    request = _compose_at(InterviewStep.SCENARIOS)

    assert (request.step, request.steps) == (5, 5)


def test_criteria_cards_carry_no_metric_annotation() -> None:
    request = _compose_at(InterviewStep.CRITERIA)

    components = [component for card in request.cards for component in card.components]
    assert components
    assert all("note" not in component.model_dump() for component in components)
    assert all(
        "measured by:" not in component.text
        for component in components
        if hasattr(component, "text")
    )


def test_a_criterion_is_three_labelled_rows_with_dividers_between() -> None:
    """Each acceptance criterion is drawn as Given/When/Then labelled rows, and a divider
    separates one criterion from the next so a multi-criterion behaviour does not read as one
    undifferentiated block. The divider sits *between* criteria only — never leading or trailing.

    EB-1 in the fixture is a ticked behaviour with two criteria, so its card is the case that
    needs the boundary; EB-2 is unticked and draws a note instead of criteria.
    """
    request = _compose_at(InterviewStep.CRITERIA)
    card = next(card for card in request.cards if card.id == "EB-1")

    kinds = [(c.type.value, getattr(c, "label", None)) for c in card.components]
    assert kinds == [
        ("text", None),
        ("text", "Name"),
        ("text", "Given"),
        ("text", "When"),
        ("text", "Then"),
        ("divider", None),
        ("text", "Name"),
        ("text", "Given"),
        ("text", "When"),
        ("text", "Then"),
    ]


def test_the_terminal_step_carries_no_header() -> None:
    """DONE is off the interview list, so a request stamped there draws no header."""
    from metis.wizard.application import screens
    from metis.wizard.contracts import ChatRequest

    request = ChatRequest(prompt="done")
    screens.stamp_step(request, InterviewStep.DONE)

    assert (request.title, request.step, request.steps) == (None, None, None)


def test_a_mid_step_form_inherits_the_parent_steps_header() -> None:
    """Adding a persona mid-step keeps the personas header, not a new one."""
    from metis.wizard.contracts import ChoiceResponse

    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = InterviewState(
        id="s", profile=research_assistant(), step=InterviewStep.PERSONAS
    )
    screen = driver.compose(state)
    state.pending = screen

    add = next(o for o in screen.options if o.id.action == "add")
    driver.handle(state, screen, ChoiceResponse(selected=[str(add.id)]))

    form = state.pending
    assert form is not None
    assert (form.title, form.step, form.steps) == ("Personas", 4, 5)


def test_the_persona_add_form_keeps_the_name_and_description_and_generates_an_id() -> (
    None
):
    """One submission adds one Persona with a stable generated id."""
    from metis.wizard.contracts import ChoiceResponse, FormResponse

    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()
    before = len(profile.personas)
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.PERSONAS,
        issued_ids=collect_profile_ids(profile),
    )
    screen = driver.compose(state)
    state.pending = screen

    add = next(o for o in screen.options if o.id.action == "add")
    driver.handle(state, screen, ChoiceResponse(selected=[str(add.id)]))
    form = state.pending
    assert form is not None
    assert [f.id for f in form.fields] == ["name", "description"]

    driver.handle(
        state,
        form,
        FormResponse(
            values={
                "name": "Careful reviewer",
                "description": "Second-guesses each decision.",
            }
        ),
    )

    added = profile.personas[-1]
    assert len(profile.personas) == before + 1
    assert added.id == "P-1"
    assert added.name == "Careful reviewer"
    assert added.description == "Second-guesses each decision."
    assert added.id in state.user_typed


def test_the_behaviour_add_form_is_scoped_to_the_selected_task() -> None:
    """A manual Behaviour keeps the Task target from the screen through submission."""
    from metis.wizard.contracts import FormResponse

    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.BEHAVIOURS,
        issued_ids=collect_profile_ids(profile),
    )
    screen = driver.compose(state)
    state.pending = screen
    add = next(
        option
        for option in screen.options
        if option.id.action == "add" and option.id.target == "T-2"
    )
    driver.handle(state, screen, ChoiceResponse(selected=[str(add.id)]))

    form = state.pending
    assert form is not None and form.target == "T-2"
    assert [field.id for field in form.fields] == ["name", "description"]
    before_t1 = [behaviour.id for behaviour in profile.task("T-1").behaviours]  # type: ignore[union-attr]
    driver.handle(
        state,
        form,
        FormResponse(
            values={
                "name": "Recover gracefully",
                "description": "Stops safely after a failed search.",
            }
        ),
    )

    added = profile.task("T-2").behaviours[-1]  # type: ignore[union-attr]
    assert (added.id, added.name, added.description) == (
        "EB-4",
        "Recover gracefully",
        "Stops safely after a failed search.",
    )
    assert added.measured is True
    assert [behaviour.id for behaviour in profile.task("T-1").behaviours] == before_t1  # type: ignore[union-attr]
    assert {"EB-4"} <= state.issued_ids
    assert {"EB-4"} <= state.user_typed


def test_a_behaviour_form_with_a_stale_or_missing_task_target_changes_nothing() -> None:
    from metis.wizard.contracts import FormField, FormRequest, FormResponse

    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)
    before = profile.model_copy(deep=True)
    form = FormRequest(
        prompt="Add a Behaviour",
        target="T-404",
        fields=[
            FormField(id="name", label="Name"),
            FormField(id="description", label="Description"),
        ],
    )
    driver.handle(
        state,
        form,
        FormResponse(values={"name": "Orphan", "description": "Must not land."}),
    )
    assert profile == before
    assert driver.pending_warnings

    driver.pending_warnings.clear()
    no_target = form.model_copy(update={"target": None})
    driver.handle(
        state,
        no_target,
        FormResponse(values={"name": "Orphan", "description": "Must not land."}),
    )
    assert profile == before
    assert driver.pending_warnings


# ── persona ids are the visible and referenced labels ───────────────────────


def test_a_persona_name_is_visible_and_its_id_is_the_reference() -> None:
    """Cards and chips show Persona names while scenario references keep stable ids."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()

    personas = driver.compose(
        InterviewState(id="s", profile=profile, step=InterviewStep.PERSONAS)
    )
    titles = {c.id: c.title for c in personas.cards}
    assert titles == {
        "cooperative-delegator": "Cooperative delegator",
        "impatient-executive": "Impatient executive",
    }

    from metis.wizard.contracts import CardOptionGroup

    scenarios = driver.compose(
        InterviewState(id="s", profile=profile, step=InterviewStep.SCENARIOS)
    )
    run_as = next(
        comp
        for card in scenarios.cards
        if card.id == "S-1"
        for comp in card.components
        if isinstance(comp, CardOptionGroup) and comp.label == "Run as"
    )
    chips = {opt.id.via: opt.label for opt in run_as.options}
    assert chips["cooperative-delegator"] == "Cooperative delegator"
    assert chips["impatient-executive"] == "Impatient executive"
    assert profile.scenario("S-1").persona_refs == list(chips)  # type: ignore[union-attr]


def test_shared_review_screens_show_names_and_descriptions() -> None:
    driver = StepDriver(interviewer=ScriptedInterviewer())
    profile = research_assistant()

    behaviours = driver.compose(
        InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)
    )
    assert behaviours.cards[0].title == "Cite factual claims"
    assert (
        behaviours.cards[0].components[0].text
        == "Cites a source for every factual claim"
    )  # type: ignore[union-attr]

    personas = driver.compose(
        InterviewState(id="s", profile=profile, step=InterviewStep.PERSONAS)
    )
    assert personas.cards[0].title == "Cooperative delegator"
    assert personas.cards[0].components[0].text.startswith("A policy analyst")  # type: ignore[union-attr]

    scenarios = driver.compose(
        InterviewState(id="s", profile=profile, step=InterviewStep.SCENARIOS)
    )
    assert scenarios.cards[0].title == "Supported literature review"
    assert (
        scenarios.cards[0].components[0].text.startswith("Ask for a literature review")
    )  # type: ignore[union-attr]


def test_drafted_behaviours_start_measured_on_the_behaviour_screen() -> None:
    """The combined Behaviour screen reviews the draft and asks which to measure in one place:
    every drafted behaviour starts measured, so each card draws a ticked measurement box, and
    the screen carries the measurement instruction rather than a bare review prompt."""
    profile = ProductProfile(
        product=Product(name="Agent", description="An agent.", users="Operators")
    )
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)

    request = driver.compose(state)

    assert all(behaviour.measured for behaviour in profile.behaviours())
    assert all(card.selected for card in request.cards)
    assert all(card.options[0].selected for card in request.cards)
    assert request.instruction is not None
    assert "measure" in request.instruction.lower()


# ── the scenarios gates ─────────────────────────────────────────────────────


def _scenarios_screen(profile):
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = InterviewState(id="s", profile=profile, step=InterviewStep.SCENARIOS)
    return driver.compose(state)


def test_the_footer_matches_the_harness_expansion() -> None:
    profile = research_assistant()

    request = _scenarios_screen(profile)

    assert f"Total: {profile.trial_count()} trials" == request.footer
    assert "scenarios" not in (request.footer or "")
    assert "pairs" not in (request.footer or "")

    cards = {card.id: card for card in request.cards}
    assert cards["S-1"].trials == 6
    assert cards["S-2"].trials == 3


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


def test_trial_count_is_zero_when_a_scenario_has_no_persona() -> None:
    profile = research_assistant()
    profile.scenario("S-1").persona_refs = []  # type: ignore[union-attr]

    request = _scenarios_screen(profile)
    card = next(card for card in request.cards if card.id == "S-1")

    assert card.trials == 0
    assert request.footer == "Total: 3 trials"


def test_trial_count_uses_the_singular_for_one() -> None:
    profile = research_assistant()
    profile.scenario("S-1").persona_refs = []  # type: ignore[union-attr]
    profile.scenario("S-2").num_trials = 1  # type: ignore[union-attr]

    request = _scenarios_screen(profile)
    card = next(card for card in request.cards if card.id == "S-2")

    assert card.trials == 1
    assert request.footer == "Total: 1 trial"


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
    state = InterviewState(id="s", profile=profile, step=InterviewStep.SCENARIOS)
    return driver, state, driver.compose(state)


def test_a_trial_edit_recomposes_the_scenario_total() -> None:
    driver, state, request = _scenario_edit_state()

    driver.handle(state, request, ChoiceResponse(values={"trials:S-2": 7}))

    assert state.profile.scenario("S-2").num_trials == 7  # type: ignore[union-attr]
    refreshed = driver.compose(state)
    assert refreshed.footer == "Total: 13 trials"  # 2×3 + 1×7
    scenario_card = next(card for card in refreshed.cards if card.id == "S-2")
    assert next(c for c in scenario_card.components if c.type == "number").value == 7
    assert scenario_card.trials == 7


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


def test_the_behaviour_screen_gates_continue_on_at_least_one_measured() -> None:
    """Leaving behaviours unmeasured is a choice, not a mistake to flag, so the screen raises
    no warning either way. But at least one behaviour must be measured to have anything to
    write criteria for, so Continue is disabled while nothing is measured and enabled once one
    is."""
    profile = research_assistant()
    for behaviour in profile.behaviours():
        behaviour.measured = False
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)

    request = driver.compose(state)

    assert not request.warnings
    assert not next(o for o in request.options if o.id.action == "continue").enabled

    profile.behaviour("EB-1").measured = True  # type: ignore[union-attr]
    request = driver.compose(state)

    assert not request.warnings
    assert next(o for o in request.options if o.id.action == "continue").enabled


# ── going back ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "destination", "expected_prompt"),
    [
        (
            InterviewStep.CRITERIA,
            InterviewStep.BEHAVIOURS,
            "Review the behaviour draft.",
        ),
        (
            InterviewStep.SCENARIOS,
            InterviewStep.PERSONAS,
            "Review the personas.",
        ),
    ],
)
def test_every_visible_back_transition_restores_its_destination(
    source: InterviewStep, destination: InterviewStep, expected_prompt: str
) -> None:
    profile = research_assistant()
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    driver._step_messages = {
        InterviewStep.BEHAVIOURS: "Review the behaviour draft.",
        InterviewStep.CRITERIA: "Review the acceptance criteria.",
        InterviewStep.PERSONAS: "Review the personas.",
        InterviewStep.SCENARIOS: "Review the scenarios.",
    }
    state = InterviewState(
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
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)

    request = driver.compose(state)

    assert request.prompt == "Here's the current draft."


def test_going_back_regenerates_nothing_that_already_exists() -> None:
    """Continue generates only what is missing; existing criteria are left alone."""
    profile = research_assistant()
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)
    before = profile.behaviour("EB-1").criteria[0].description.then  # type: ignore[union-attr]

    driver._advance(state)  # the Continue that generates

    assert "draft_criteria" not in interviewer.calls  # nothing was missing
    assert profile.behaviour("EB-1").criteria[0].description.then == before  # type: ignore[union-attr]


def test_unticking_then_continuing_generates_only_the_gap() -> None:
    profile = research_assistant()
    profile.behaviour("EB-1").criteria = []  # type: ignore[union-attr]
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)

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

    def chat(self, profile, step, text, target):
        raise ModelOutputError("three attempts, all malformed")


def test_a_total_failure_warns_and_loses_nothing() -> None:
    profile = research_assistant()
    profile.personas = []
    driver = StepDriver(interviewer=BrokenInterviewer())
    state = InterviewState(id="s", profile=profile, step=InterviewStep.PERSONAS)

    request = driver.compose(state)

    runtime = [w for w in request.warnings if w.source is WarningSource.RUNTIME]
    assert runtime and "nothing you've decided has been lost" in runtime[0].text.lower()
    assert not runtime[0].blocking
    assert state.profile.tasks  # the profile is intact
    assert state.step is InterviewStep.PERSONAS  # and we did not advance past it


def test_a_chat_failure_warns_and_loses_nothing() -> None:
    """A chat is a model call like any other: when all its retries fail, it degrades to a
    warning and touches nothing, rather than crashing the turn."""
    profile = research_assistant()
    before = profile.model_copy(deep=True)
    driver = StepDriver(interviewer=BrokenInterviewer())
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.CRITERIA,
        issued_ids=collect_profile_ids(profile),
    )

    driver.handle(
        state,
        ChatRequest(prompt="q", multiline=True),
        ChatResponse(text="change something"),
    )

    runtime = [w for w in driver.pending_warnings if w.source is WarningSource.RUNTIME]
    assert runtime and "left your profile exactly as it is" in runtime[0].text.lower()
    assert not runtime[0].blocking
    assert state.profile == before  # nothing applied


# ── responses that cost no model call ──────────────────────────────────────


def test_ticking_costs_no_model_call() -> None:
    profile = research_assistant()
    interviewer = ScriptedInterviewer()
    driver = StepDriver(interviewer=interviewer)
    state = InterviewState(id="s", profile=profile, step=InterviewStep.BEHAVIOURS)
    request = driver.compose(state)
    interviewer.calls.clear()

    driver.handle(state, request, ChoiceResponse(selected=["tick:EB-2"]))

    assert interviewer.calls == []
    assert profile.behaviour("EB-2").measured is True  # type: ignore[union-attr]


# ── a reworded criterion re-maps its metric, silently ───────────────────────

_AC1 = "tasks[T-1].behaviours[EB-1].criteria[AC-1-1].description.then"


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
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.CRITERIA,
        issued_ids=collect_profile_ids(profile),
    )

    driver.handle(
        state, ChatRequest(prompt="q", multiline=True), ChatResponse(text="use routing")
    )

    assert matcher.matched == ["AC-1-1"]  # only the reworded criterion
    assert (
        profile.behaviour("EB-1").criteria[0].metric_fqn  # type: ignore[union-attr]
        == "metis.library.metrics.routing.RoutingAccuracyMetric"
    )


# ── a scoped criteria chat stays on its own behaviour ────────────────────────

_EB1_THEN = "tasks[T-1].behaviours[EB-1].criteria[AC-1-1].description.then"
_EB2_THEN = "tasks[T-1].behaviours[EB-2].criteria[AC-2-1].description.then"


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
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.CRITERIA,
        issued_ids=collect_profile_ids(profile),
    )

    before_eb2 = profile.behaviour("EB-2").criteria[0].description.then  # type: ignore[union-attr]
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
        profile.behaviour("EB-1").criteria[0].description.then  # type: ignore[union-attr]
        == "it names the routing decision"
    )
    assert profile.behaviour("EB-2").criteria[0].description.then == before_eb2  # type: ignore[union-attr]
    assert any(w.source is WarningSource.RUNTIME for w in driver.pending_warnings)


# ── "Suggest one for me": one clean add, or nothing ──────────────────────────


def _suggest_on(profile, interviewer, matcher=None):
    """Drive the real "Suggest one for me" control on EB-1's card, the way the door would.

    Composes the criteria screen, finds the `another` option scoped to EB-1, and clicks it —
    so the behaviour id reaches the driver exactly as `OptionId.target`, not hand-fed."""
    from metis.wizard.contracts import ChoiceResponse

    driver = StepDriver(interviewer=interviewer, matcher=matcher)
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.CRITERIA,
        issued_ids=collect_profile_ids(profile),
    )
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
                        "name": "Wrong target",
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
    assert [f.id for f in form.fields] == ["name", "given", "when", "then"]
    driver.handle(state, form, FormResponse(values=values))


def test_writing_two_criteria_by_hand_produces_two_distinct_ones() -> None:
    """Manual entry appends a FORM criterion under the card's behaviour, verbatim. A second
    submission gets its own scoped id rather than overwriting the first — the append-nothing
    bug is what this guards against."""
    profile = research_assistant()
    matcher = RecordingMatcher()
    driver = StepDriver(interviewer=ScriptedInterviewer(), matcher=matcher)
    state = InterviewState(
        id="s",
        profile=profile,
        step=InterviewStep.CRITERIA,
        issued_ids=collect_profile_ids(profile),
    )

    _type_one(
        driver,
        state,
        {
            "name": "Long report outcome",
            "given": "a long report",
            "when": "it is asked to summarise",
            "then": "it keeps every citation",
        },
    )
    _type_one(
        driver,
        state,
        {
            "name": "Consistent follow-up",
            "given": "a follow-up",
            "when": "it answers again",
            "then": "it stays consistent",
        },
    )

    eb1 = profile.behaviour("EB-1")
    assert [c.id for c in eb1.criteria] == ["AC-1-1", "AC-1-2", "AC-1-3", "AC-1-4"]  # type: ignore[union-attr]
    fresh = eb1.criteria[-2:]  # type: ignore[union-attr]
    assert [c.description.given for c in fresh] == [
        "a long report",
        "a follow-up",
    ]  # verbatim, in order
    assert {c.id for c in fresh} <= state.user_typed
    assert matcher.matched == ["AC-1-3", "AC-1-4"]  # each new one matched, once
