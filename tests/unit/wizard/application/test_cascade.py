"""What an edit costs the work derived from it."""

from metis.wizard.application import cascade
from metis.wizard.application.driver import DriverState, StepDriver
from metis.wizard.contracts import (
    ChatRequest,
    ChoiceResponse,
    Patch,
    PatchOp,
    PatchOrigin,
    Specification,
    Target,
)
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.context import interview_context
from tests.fixtures.wizard.scripted import ScriptedInterviewer
from tests.fixtures.wizard.specifications import research_assistant

EB1_DESCRIPTION = "features[F-1].behaviours[EB-1].description"


def edit(path: str, value="reworded") -> Patch:
    return Patch(op=PatchOp.SET, path=path, value=value, origin=PatchOrigin.MODEL)


def a_state(step=InterviewStep.CRITERIA) -> DriverState:
    return DriverState(
        specification=research_assistant(), context=interview_context(), step=step
    )


# ── what asks, and in what order ───────────────────────────────────────────


def test_rewording_a_behaviour_asks_twice_in_sequence() -> None:
    """Criteria first, then each scenario covering it — nearest the edit, then further away."""
    specification = research_assistant()

    questions = cascade.questions_for(specification, [edit(EB1_DESCRIPTION)])

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


def test_editing_the_target_reaches_the_whole_tree() -> None:
    for path in ("target.description", "target.detail"):
        questions = cascade.questions_for(research_assistant(), [edit(path)])

        assert [q.kind for q in questions] == ["tree"]


def test_initial_target_capture_does_not_invalidate_its_own_draft() -> None:
    specification = Specification(target=Target(name="X", description="", users=""))

    questions = cascade.questions_for(
        specification,
        [
            edit("target.description", "A new target"),
            edit("target.detail", "Tools"),
        ],
    )

    assert questions == []


def test_description_and_detail_edits_ask_about_the_tree_once() -> None:
    specification = research_assistant()

    questions = cascade.questions_for(
        specification,
        [edit("target.description"), edit("target.detail")],
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
    specification = research_assistant()

    nothing = [
        edit("features[F-1].behaviours[EB-1].measured", False),
        edit("personas[cooperative-delegator].description", "different words"),
        edit("tasks[TC-001].behaviour_refs", ["AC-1-1"]),
        edit("tasks[TC-001].num_trials", 5),
        edit("tasks[TC-001].fixtures", ["a.pdf"]),
        edit("target.name", "New name"),
    ]

    assert cascade.questions_for(specification, nothing) == []


def test_personas_are_reached_by_nothing() -> None:
    """They come from *all* criteria, so no single edit above them triggers a question."""
    specification = research_assistant()

    questions = cascade.questions_for(
        specification,
        [
            edit(
                "features[F-1].behaviours[EB-1].criteria[AC-1-1].description",
                "x",
            )
        ],
    )

    assert not any(q.kind == "persona" for q in questions)


def test_each_thing_is_asked_about_once() -> None:
    """Two edits to the same behaviour is still one question about its criteria."""
    specification = research_assistant()

    questions = cascade.questions_for(
        specification, [edit(EB1_DESCRIPTION), edit(EB1_DESCRIPTION)]
    )

    assert len(questions) == 2  # criteria + S-1, not four


# ── what regenerating clears ───────────────────────────────────────────────


def test_regenerating_keeps_text_the_user_typed() -> None:
    """FORM content came in through a form and is used as-is."""
    specification = research_assistant()
    behaviour = specification.behaviour("EB-3")
    assert behaviour is not None
    cascade.clear_for_regeneration(
        specification,
        cascade.Question(text="", subject="EB-3", kind="criteria"),
        {"AC-3-1"},
    )

    assert len(behaviour.criteria) == 1  # the user's survived


def test_regenerating_clears_what_the_model_wrote() -> None:
    specification = research_assistant()
    behaviour = specification.behaviour("EB-1")
    assert behaviour is not None and len(behaviour.criteria) == 2

    cascade.clear_for_regeneration(
        specification, cascade.Question(text="", subject="EB-1", kind="criteria"), set()
    )

    assert behaviour.criteria == []  # both were CHAT-authored


def test_a_target_edit_clears_everything_derived_from_it() -> None:
    """Features and scenarios were all derived from the target description."""
    specification = research_assistant()

    cascade.clear_for_regeneration(
        specification,
        cascade.Question(text="", subject="target.description", kind="tree"),
        set(),
    )

    assert specification.features == []
    assert specification.scenarios == []


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
        specification=Specification(
            target=Target(name="X", description="Answers research questions.", users="")
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
    before = len(state.specification.behaviour("EB-1").criteria)  # type: ignore[union-attr]

    driver._answer_question(state, ChoiceResponse(selected=["keep:EB-1"]))

    assert len(state.specification.behaviour("EB-1").criteria) == before  # type: ignore[union-attr]


def test_answering_regenerate_lands_in_a_state_the_screens_already_draw() -> None:
    """A ticked behaviour with no criteria is what Continue fills in."""
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state()
    driver._run(state, _result_editing_eb1())

    driver._answer_question(state, ChoiceResponse(selected=["regenerate:EB-1"]))

    behaviour = state.specification.behaviour("EB-1")
    assert behaviour is not None
    assert behaviour.criteria  # regenerated, not left empty


def test_reviewing_a_target_edit_returns_to_the_draft_screen() -> None:
    driver = StepDriver(interviewer=ScriptedInterviewer())
    state = a_state(step=InterviewStep.CRITERIA)
    question = cascade.questions_for(state.specification, [edit("target.detail")])[0]
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
    dumped = state.specification.model_dump_json()
    assert "stale" not in dumped and "out_of_date" not in dumped


def _result_editing_eb1():
    from metis.wizard.contracts import StepResult

    return StepResult(message="Reworded.", patches=[edit(EB1_DESCRIPTION)])


# ── the Target review form after Back ──────────────────────────────────────


def _submit_target_review(
    changes: dict[str, str], *, stored_description: str | None = None
) -> tuple[DriverState, StepDriver]:
    from metis.wizard.application import screens
    from metis.wizard.contracts import FormResponse

    state = a_state(step=InterviewStep.CLARIFY)
    if stored_description is not None:
        state.specification.target.description = stored_description
    driver = StepDriver(interviewer=ScriptedInterviewer())
    form = screens.target_review_form(state.specification)
    values = {field.id: field.value for field in form.fields}
    values.update(changes)
    driver.handle(state, form, FormResponse(values=values))
    return state, driver


def test_a_target_description_edit_on_review_asks_the_tree_question() -> None:
    state, driver = _submit_target_review(
        {"target.description": "An agent that drafts policy briefs."}
    )

    assert [question.kind for question in driver.pending_questions] == ["tree"]
    assert state.specification.target.description == (
        "An agent that drafts policy briefs."
    )
    assert state.specification.features  # kept until the user answers
    assert state.step is InterviewStep.BEHAVIOURS


def test_a_target_name_edit_or_no_edit_on_review_asks_nothing() -> None:
    renamed, renamed_driver = _submit_target_review({"target.name": "Librarian"})
    unchanged, unchanged_driver = _submit_target_review({})

    assert renamed_driver.pending_questions == []
    assert renamed.specification.target.name == "Librarian"
    assert unchanged_driver.pending_questions == []
    assert unchanged.specification == research_assistant()
    assert unchanged.step is InterviewStep.BEHAVIOURS


def test_a_stored_value_with_surrounding_whitespace_is_unchanged_on_review() -> None:
    stored = research_assistant().target.description + "  \n"
    state, driver = _submit_target_review({}, stored_description=stored)

    assert driver.pending_questions == []
    assert state.specification.target.description == stored
    assert state.step is InterviewStep.BEHAVIOURS
