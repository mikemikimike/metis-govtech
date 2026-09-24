"""What an edit costs the work derived from it."""

from metis.wizard.application import cascade
from metis.wizard.application.driver import DriverState, StepDriver
from metis.wizard.contracts import (
    ChatRequest,
    ChoiceResponse,
    Patch,
    PatchOp,
    PatchOrigin,
    Product,
    ProductProfile,
)
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.context import interview_context
from tests.fixtures.wizard.profiles import research_assistant
from tests.fixtures.wizard.scripted import ScriptedInterviewer

EB1_DESCRIPTION = "tasks[T-1].behaviours[EB-1].description"


def edit(path: str, value="reworded") -> Patch:
    return Patch(op=PatchOp.SET, path=path, value=value, origin=PatchOrigin.MODEL)


def a_state(step=InterviewStep.CRITERIA) -> DriverState:
    return DriverState(
        profile=research_assistant(), context=interview_context(), step=step
    )


# ── what asks, and in what order ───────────────────────────────────────────


def test_rewording_a_behaviour_asks_twice_in_sequence() -> None:
    """Criteria first, then each scenario covering it — nearest the edit, then further away."""
    profile = research_assistant()

    questions = cascade.questions_for(profile, [edit(EB1_DESCRIPTION)])

    assert [q.kind for q in questions] == ["criteria", "scenario"]
    assert questions[0].subject == "EB-1"
    assert questions[1].subject == "S-1"


def test_the_wizard_offers_no_opinion_on_whether_they_still_hold() -> None:
    """It asks either way. A wrong silent judgement is the failure being avoided."""
    questions = cascade.questions_for(research_assistant(), [edit(EB1_DESCRIPTION)])

    request = questions[0].to_request()
    actions = [o.id.action for o in request.options]

    assert actions == ["keep", "regenerate", "edit"]
    assert request.multi is False


def test_editing_the_product_reaches_the_whole_tree() -> None:
    for path in ("product.description", "product.detail"):
        questions = cascade.questions_for(research_assistant(), [edit(path)])

        assert [q.kind for q in questions] == ["tree"]


def test_initial_product_capture_does_not_invalidate_its_own_draft() -> None:
    profile = ProductProfile(product=Product(name="X", description="", users=""))

    questions = cascade.questions_for(
        profile,
        [
            edit("product.description", "A new product"),
            edit("product.detail", "Tools"),
        ],
    )

    assert questions == []


def test_description_and_detail_edits_ask_about_the_tree_once() -> None:
    profile = research_assistant()

    questions = cascade.questions_for(
        profile,
        [edit("product.description"), edit("product.detail")],
    )

    assert [question.kind for question in questions] == ["tree"]
    request = questions[0].to_request()
    assert [option.id.action for option in request.options] == [
        "keep",
        "regenerate",
        "review",
    ]


def test_edits_that_derive_nothing_ask_nothing() -> None:
    """The tick is scope, not content. Personas are referenced by id, not by text."""
    profile = research_assistant()

    nothing = [
        edit("tasks[T-1].behaviours[EB-1].measured", False),
        edit("personas[cooperative-delegator].description", "different words"),
        edit("scenarios[S-1].behaviour_refs", ["EB-1"]),
        edit("scenarios[S-1].num_trials", 5),
        edit("scenarios[S-1].fixtures", ["a.pdf"]),
        edit("product.name", "New name"),
    ]

    assert cascade.questions_for(profile, nothing) == []


def test_personas_are_reached_by_nothing() -> None:
    """They come from *all* criteria, so no single edit above them triggers a question."""
    profile = research_assistant()

    questions = cascade.questions_for(
        profile,
        [
            edit(
                "tasks[T-1].behaviours[EB-1].criteria[AC-1-1].description.then",
                "x",
            )
        ],
    )

    assert not any(q.kind == "persona" for q in questions)


def test_each_thing_is_asked_about_once() -> None:
    """Two edits to the same behaviour is still one question about its criteria."""
    profile = research_assistant()

    questions = cascade.questions_for(
        profile, [edit(EB1_DESCRIPTION), edit(EB1_DESCRIPTION)]
    )

    assert len(questions) == 2  # criteria + S-1, not four


# ── what regenerating clears ───────────────────────────────────────────────


def test_regenerating_keeps_text_the_user_typed() -> None:
    """FORM content came in through a form and is used as-is."""
    profile = research_assistant()
    behaviour = profile.behaviour("EB-3")
    assert behaviour is not None
    cascade.clear_for_regeneration(
        profile,
        cascade.Question(text="", subject="EB-3", kind="criteria"),
        {"AC-3-1"},
    )

    assert len(behaviour.criteria) == 1  # the user's survived


def test_regenerating_clears_what_the_model_wrote() -> None:
    profile = research_assistant()
    behaviour = profile.behaviour("EB-1")
    assert behaviour is not None and len(behaviour.criteria) == 2

    cascade.clear_for_regeneration(
        profile, cascade.Question(text="", subject="EB-1", kind="criteria"), set()
    )

    assert behaviour.criteria == []  # both were CHAT-authored


def test_a_product_edit_clears_everything_derived_from_it() -> None:
    """Tasks and scenarios were all derived from the product description."""
    profile = research_assistant()

    cascade.clear_for_regeneration(
        profile,
        cascade.Question(text="", subject="product.description", kind="tree"),
        set(),
    )

    assert profile.tasks == []
    assert profile.scenarios == []


# ── the driver asks in the same turn ───────────────────────────────────────


def test_the_question_is_asked_before_the_next_screen() -> None:
    """Same turn, no flag left behind — which is what stops this being staleness tracking."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state()

    driver._run(state, _result_editing_eb1())

    assert driver.pending_questions
    request = driver.compose(state)
    assert "Regenerate" in str([o.label for o in request.options])  # type: ignore[union-attr]


def test_chat_on_the_initial_draft_opens_free_text() -> None:
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = DriverState(
        profile=ProductProfile(
            product=Product(
                name="X", description="Answers research questions.", users=""
            )
        ),
        context=interview_context(),
        step=InterviewStep.BEHAVIOURS,
    )
    request = driver.compose(state)

    assert driver.pending_questions == []
    driver.handle(state, request, ChoiceResponse(selected=["chat"]))

    assert isinstance(state.pending, ChatRequest)
    assert state.pending.prompt.startswith("What would you like to change?")
    # The prompt is door-neutral: `.done` is the CLI reader's own input marker, not package
    # wording, so a door with a Send button never shows it.
    assert ".done" not in state.pending.prompt
    assert state.pending.multiline


def test_answering_keep_changes_nothing() -> None:
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state()
    driver._run(state, _result_editing_eb1())
    before = len(state.profile.behaviour("EB-1").criteria)  # type: ignore[union-attr]

    driver._answer_question(state, ChoiceResponse(selected=["keep:EB-1"]))

    assert len(state.profile.behaviour("EB-1").criteria) == before  # type: ignore[union-attr]


def test_answering_regenerate_lands_in_a_state_the_screens_already_draw() -> None:
    """A ticked behaviour with no criteria is what Continue fills in."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state()
    driver._run(state, _result_editing_eb1())

    driver._answer_question(state, ChoiceResponse(selected=["regenerate:EB-1"]))

    behaviour = state.profile.behaviour("EB-1")
    assert behaviour is not None
    assert behaviour.criteria  # regenerated, not left empty


def test_reviewing_a_product_edit_returns_to_the_draft_screen() -> None:
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state(step=InterviewStep.CRITERIA)
    question = cascade.questions_for(state.profile, [edit("product.detail")])[0]
    driver.pending_questions = [question]

    driver._answer_question(
        state, ChoiceResponse(selected=[f"review:{question.subject}"])
    )

    assert state.step is InterviewStep.BEHAVIOURS
    assert driver.pending_questions == []


def test_no_flag_survives_the_turn() -> None:
    """Nothing carries an "out of date" badge around the interface afterwards."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state()
    driver._run(state, _result_editing_eb1())

    while driver.pending_questions:
        driver._answer_question(state, ChoiceResponse(selected=["keep:x"]))

    assert driver.pending_questions == []
    dumped = state.profile.model_dump_json()
    assert "stale" not in dumped and "out_of_date" not in dumped


def _result_editing_eb1():
    from metis.wizard.contracts import StepResult

    return StepResult(message="Reworded.", patches=[edit(EB1_DESCRIPTION)])
