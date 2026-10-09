"""The Interview operation as a stateless transaction."""

from __future__ import annotations

import pytest

from metis.wizard import (
    CompilationError,
    InterviewEndRequest,
    InterviewErrorCode,
    InterviewFailure,
    InterviewStartRequest,
    InterviewSuccess,
    InterviewTurnRequest,
    compile_specification,
    derive_stage,
    handle_interview,
)
from metis.wizard.application.driver import DriverState
from metis.wizard.application.interviewer import InterviewerOutputError
from metis.wizard.application.screens import behaviours_screen, scenarios_screen
from metis.wizard.application.turn import _reconcile_locks
from metis.wizard.contracts import (
    ChatResponse,
    ChoiceRequest,
    ChoiceResponse,
    ClarifyResult,
    FormRequest,
    FormResponse,
    InterviewDocument,
    Option,
    OptionId,
    Patch,
    PatchOp,
    Perspective,
    Product,
    Specification,
)
from metis.wizard.contracts.interview_state import HISTORY_LIMIT, InterviewState, Turn
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.context import interview_context
from tests.fixtures.wizard.scripted import ScriptedInterviewer, ScriptedMatcher
from tests.fixtures.wizard.specifications import research_assistant


def _start(
    *,
    interviewer=None,
    perspective=Perspective.END_USER,
    known_capability_ids=None,
    capability_confidence="low",
    documents=None,
):
    return handle_interview(
        InterviewStartRequest(
            description="A research assistant",
            perspective=perspective,
            known_capability_ids=(
                [] if known_capability_ids is None else known_capability_ids
            ),
            capability_confidence=capability_confidence,
            documents=documents or [],
        ),
        interviewer=interviewer or ScriptedInterviewer(),
        matcher=None,
    )


def _turn(state, response, *, request_id=None, interviewer=None):
    return handle_interview(
        InterviewTurnRequest(
            state=state,
            request_id=request_id or state.pending.request_id,
            response=response,
        ),
        interviewer=interviewer or ScriptedInterviewer(),
        matcher=None,
    )


def _end(state, *, interviewer=None, matcher=None):
    return handle_interview(
        InterviewEndRequest(state=state),
        interviewer=interviewer or ScriptedInterviewer(),
        matcher=matcher,
    )


def _empty_specification() -> Specification:
    return Specification(product=Product(name="", description="", users=""))


def _pending_choice(request_id: str = "req-1") -> InterviewState:
    return InterviewState(
        specification=research_assistant(),
        context=interview_context(),
        pending=ChoiceRequest(
            prompt="Do these look right?",
            options=[Option(id=OptionId(action="continue"), label="Continue")],
            request_id=request_id,
            stage=InterviewStep.BEHAVIOURS,
        ),
    )


def test_start_records_the_raw_description_as_the_first_user_turn() -> None:
    result = _start()

    assert isinstance(result, InterviewSuccess)
    assert result.state.history[0].role == "user"
    assert result.state.history[0].text == "A research assistant"
    assert result.state.context.opening_description == "A research assistant"
    assert result.state.pending is not None


def test_start_records_a_perspective_and_reuses_it_on_the_next_turn() -> None:
    class RecordingInterviewer(ScriptedInterviewer):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[Perspective] = []

        def clarify(self, specification, history, context=None):
            assert context is not None
            self.seen.append(context.perspective)
            return super().clarify(specification, history, context)

    interviewer = RecordingInterviewer()
    started = _start(interviewer=interviewer, perspective=Perspective.SECURITY)
    assert isinstance(started, InterviewSuccess)
    assert started.state.context.perspective is Perspective.SECURITY

    continued = _turn(
        started.state,
        ChatResponse(text="It answers policy questions."),
        interviewer=interviewer,
    )

    assert isinstance(continued, InterviewSuccess)
    assert interviewer.seen
    assert all(perspective is Perspective.SECURITY for perspective in interviewer.seen)


def test_start_records_capability_evidence_and_keeps_it_on_a_later_turn() -> None:
    started = _start(
        known_capability_ids=["tool_use", "internet_search_access"],
        capability_confidence="medium",
    )
    assert isinstance(started, InterviewSuccess)
    evidence = started.state.context.capability_evidence
    assert [item.value for item in evidence.known_capability_ids] == [
        "tool_use",
        "internet_search_access",
    ]
    assert evidence.confidence.value == "medium"

    continued = _turn(
        started.state,
        ChatResponse(text="It searches the internal library."),
    )

    assert isinstance(continued, InterviewSuccess)
    assert continued.state.context.capability_evidence == evidence


def test_start_with_whitespace_is_rejected_before_processing() -> None:
    with pytest.raises(ValueError):
        InterviewStartRequest(
            description="  ", known_capability_ids=[], capability_confidence="low"
        )


def test_explicit_none_disables_the_configured_matcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metis.wizard.application import turn as turn_module

    class ConfiguredMatcher:
        degraded = False
        calls = 0

        def match(self, _criterion):
            self.calls += 1
            return "configured.metric"

    matcher = ConfiguredMatcher()
    monkeypatch.setattr(turn_module, "_DEFAULT_MATCHER", matcher)
    specification = research_assistant()
    specification.behaviour("EB-1").criteria = []  # type: ignore[union-attr]
    state = InterviewState(
        specification=specification,
        context=interview_context(),
        pending=ChoiceRequest(
            prompt="Review Behaviours",
            options=[Option(id=OptionId(action="continue"), label="Continue")],
            request_id="req-behaviours",
            stage=InterviewStep.BEHAVIOURS,
        ),
    )

    result = handle_interview(
        InterviewTurnRequest(
            state=state,
            request_id="req-behaviours",
            response=ChoiceResponse(selected=["continue"]),
        ),
        interviewer=ScriptedInterviewer(),
        matcher=None,
    )

    assert isinstance(result, InterviewSuccess)
    assert matcher.calls == 0
    assert result.state.specification.behaviour("EB-1").criteria[0].metric_fqn is None  # type: ignore[union-attr]


def test_a_late_answer_is_caught_by_the_request_id() -> None:
    state = _pending_choice()

    result = _turn(
        state,
        ChoiceResponse(selected=["continue"]),
        request_id="req-0",
    )

    assert isinstance(result, InterviewFailure)
    assert result.code is InterviewErrorCode.REQUEST_ID_MISMATCH
    assert result.state == state


def test_an_answer_of_the_wrong_kind_is_refused() -> None:
    state = _pending_choice()

    result = _turn(state, ChatResponse(text="hi"))

    assert isinstance(result, InterviewFailure)
    assert result.code is InterviewErrorCode.RESPONSE_TYPE_MISMATCH
    assert result.state == state


def test_an_option_the_screen_never_offered_is_refused() -> None:
    state = _pending_choice()

    result = _turn(state, ChoiceResponse(selected=["never-shown"]))

    assert isinstance(result, InterviewFailure)
    assert result.code is InterviewErrorCode.RESPONSE_NOT_OFFERED
    assert result.state == state


def test_a_behaviour_measurement_change_stays_pending_before_continue() -> None:
    specification = research_assistant()
    pending = behaviours_screen(specification, "Review Behaviours")
    pending.request_id = "req-behaviours"
    pending.stage = InterviewStep.BEHAVIOURS
    state = InterviewState(
        specification=specification, context=interview_context(), pending=pending
    )

    result = _turn(
        state,
        ChoiceResponse(selected=["tick:EB-1", "continue"]),
    )

    assert isinstance(result, InterviewSuccess)
    assert result.stage is InterviewStep.BEHAVIOURS
    assert result.state.pending is not None
    assert result.state.pending.stage is InterviewStep.BEHAVIOURS
    assert not result.state.behaviours_confirmed
    assert not result.state.specification.behaviour("EB-1").measured  # type: ignore[union-attr]


class ClarifyUnavailable(ScriptedInterviewer):
    def clarify(self, specification, history, context=None):
        raise InterviewerOutputError("three attempts, all failed")


def test_model_failure_is_retryable_with_the_state_intact() -> None:
    opening = _start()
    assert isinstance(opening, InterviewSuccess)

    result = _turn(
        opening.state,
        ChatResponse(text="a policy tool"),
        interviewer=ClarifyUnavailable(),
    )

    assert isinstance(result, InterviewFailure)
    assert result.code is InterviewErrorCode.MODEL_UNAVAILABLE
    assert result.retryable
    assert result.state == opening.state


def test_end_finishes_a_completable_interview() -> None:
    specification = research_assistant()
    specification.behaviour("EB-1").criteria[0].metric_fqn = None  # type: ignore[union-attr]
    result = _end(
        InterviewState(
            specification=specification,
            context=interview_context(),
            behaviours_confirmed=True,
        ),
        matcher=ScriptedMatcher(),
    )

    assert isinstance(result, InterviewSuccess)
    assert result.outcome == "done"
    assert result.state.confirmed
    assert result.state.pending is None
    assert result.state.specification.behaviour("EB-1").criteria[0].metric_fqn  # type: ignore[union-attr]


def test_missing_product_details_can_be_completed_before_review() -> None:
    class IncompleteInterviewer(ScriptedInterviewer):
        def clarify(self, specification, history, context=None):
            return ClarifyResult(
                done=True,
                message="",
                patches=[
                    Patch(op=PatchOp.SET, path=f"product.{key}", value="")
                    for key in ("name", "description")
                ],
            )

    interviewer = IncompleteInterviewer()
    started = _start(interviewer=interviewer)
    assert isinstance(started, InterviewSuccess)
    assert isinstance(started.state.pending, FormRequest)
    completed = _turn(
        started.state,
        FormResponse(
            values={
                "product.name": "Policy assistant",
                "product.description": "Answers policy questions.",
            }
        ),
        interviewer=interviewer,
    )
    assert isinstance(completed, InterviewSuccess)
    assert isinstance(completed.state.pending, ChoiceRequest)
    continued = _turn(
        completed.state, ChoiceResponse(selected=["continue"]), interviewer=interviewer
    )
    assert isinstance(continued, InterviewSuccess)
    assert continued.stage is InterviewStep.CRITERIA


@pytest.mark.parametrize("suggested_files", [[], ["policy.pdf"]])
def test_documents_survive_turns_and_require_file_review(
    suggested_files: list[str],
) -> None:
    documents = [
        InterviewDocument(name="policy.pdf", text="POLICY_CONTEXT_SENTINEL"),
        InterviewDocument(name="terms.md"),
    ]

    class FixtureInterviewer(ScriptedInterviewer):
        def clarify(self, specification, history, context=None):
            assert context is not None and context.documents == documents
            return super().clarify(specification, history, context)

        def draft_scenarios(self, specification, context=None):
            result = super().draft_scenarios(specification, context)
            result.patches[0].value = result.patches[0].value.model_copy(
                update={
                    "tasks": [
                        task.model_copy(update={"fixtures": suggested_files})
                        for task in result.patches[0].value.tasks
                    ]
                }
            )
            return result

    interviewer = FixtureInterviewer()
    started = _start(interviewer=interviewer, documents=documents)
    assert isinstance(started, InterviewSuccess)
    state = InterviewState.model_validate_json(started.state.model_dump_json())
    state.history = [Turn(role="user", text=f"Note {i}") for i in range(HISTORY_LIMIT)]
    continued = _turn(
        state,
        ChatResponse(text="It answers policy questions."),
        interviewer=interviewer,
    )
    assert isinstance(continued, InterviewSuccess)
    assert len(continued.state.history) == HISTORY_LIMIT
    assert continued.state.context.documents == documents

    review = _end(continued.state, interviewer=interviewer, matcher=ScriptedMatcher())
    assert isinstance(review, InterviewSuccess)
    assert review.outcome == "awaiting_response"
    assert review.stage is InterviewStep.SCENARIOS
    assert not review.state.confirmed
    assert review.state.specification.task("TC-001").fixtures == suggested_files
    uploads = [
        component
        for card in review.state.pending.cards
        for component in card.components
        if component.type == "upload"
    ]
    assert uploads and uploads[0].available == ["policy.pdf", "terms.md"]

    selected = _turn(
        review.state,
        ChoiceResponse(values={"files:TC-001": ["terms.md"]}),
        interviewer=interviewer,
    )
    assert isinstance(selected, InterviewSuccess)
    assert selected.state.specification.task("TC-001").fixtures == ["terms.md"]
    done = _turn(
        selected.state, ChoiceResponse(selected=["continue"]), interviewer=interviewer
    )
    assert isinstance(done, InterviewSuccess)
    assert done.outcome == "done" and done.state.confirmed


def test_final_continue_completes_a_ready_specification() -> None:
    specification = research_assistant()
    pending = scenarios_screen(specification, "Review scenarios")
    pending.request_id = "req-final"
    pending.stage = InterviewStep.SCENARIOS
    state = InterviewState(
        specification=specification,
        context=interview_context(),
        behaviours_confirmed=True,
        pending=pending,
    )

    result = _turn(state, ChoiceResponse(selected=["continue"]))

    assert isinstance(result, InterviewSuccess)
    assert result.outcome == "done"
    assert result.state.confirmed
    assert result.state.pending is None


def test_end_on_a_held_gate_preserves_state() -> None:
    specification = research_assistant()
    specification.scenarios = [s for s in specification.scenarios if s.id != "S-2"]
    state = InterviewState(
        specification=specification,
        context=interview_context(),
        behaviours_confirmed=True,
    )

    result = _end(state)

    assert isinstance(result, InterviewFailure)
    assert result.code is InterviewErrorCode.COMPLETION_FAILED
    assert result.state == state
    assert any(gap.subject == "EB-3" for gap in result.missing)


def test_failed_end_preserves_pending_state_for_a_later_turn() -> None:
    class DraftUnavailable(ScriptedInterviewer):
        def draft_behaviours(self, specification, history, context=None):
            raise InterviewerOutputError("three attempts, all failed")

    state = InterviewState(
        specification=Specification(
            product=Product(name="Tool", description="A tool", users="Analysts")
        ),
        context=interview_context(),
        pending=ChoiceRequest(
            prompt="Review behaviours",
            options=[Option(id=OptionId(action="continue"), label="Continue")],
            request_id="req-behaviours",
            stage=InterviewStep.BEHAVIOURS,
        ),
    )
    failed = _end(state, interviewer=DraftUnavailable())

    assert isinstance(failed, InterviewFailure)
    assert failed.code is InterviewErrorCode.MODEL_UNAVAILABLE
    assert failed.state == state

    continued = _turn(
        state,
        ChoiceResponse(selected=["continue"]),
        interviewer=ScriptedInterviewer(),
    )
    assert isinstance(continued, InterviewSuccess)
    assert continued.state.pending is not None


def test_end_on_a_completed_state_does_not_call_the_model() -> None:
    interviewer = ScriptedInterviewer()
    state = InterviewState(
        specification=research_assistant(),
        context=interview_context(),
        behaviours_confirmed=True,
        confirmed=True,
    )

    result = _end(state, interviewer=interviewer)
    repeated = (
        _end(result.state, interviewer=interviewer)
        if isinstance(result, InterviewSuccess)
        else result
    )

    assert isinstance(result, InterviewSuccess)
    assert result.outcome == "done"
    assert isinstance(repeated, InterviewSuccess)
    assert repeated.state == result.state
    assert interviewer.calls == []


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            InterviewState(
                specification=_empty_specification(), context=interview_context()
            ),
            InterviewStep.CLARIFY,
        ),
        (
            InterviewState(
                specification=research_assistant(), context=interview_context()
            ),
            InterviewStep.BEHAVIOURS,
        ),
        (
            InterviewState(
                specification=research_assistant(),
                context=interview_context(),
                behaviours_confirmed=True,
                confirmed=True,
            ),
            InterviewStep.DONE,
        ),
    ],
)
def test_derive_stage_reads_the_specification_top_to_bottom(
    state: InterviewState, expected: InterviewStep
) -> None:
    assert derive_stage(state) is expected


def test_criteria_precede_personas_when_a_measured_behaviour_lacks_them() -> None:
    specification = research_assistant()
    specification.behaviour("EB-1").criteria = []  # type: ignore[union-attr]
    state = InterviewState(
        specification=specification,
        context=interview_context(),
        behaviours_confirmed=True,
    )

    assert derive_stage(state) is InterviewStep.CRITERIA


def test_behaviour_edit_clears_both_confirmation_locks() -> None:
    specification = research_assistant()
    before = specification.model_copy(deep=True)
    working = DriverState(
        step=InterviewStep.BEHAVIOURS,
        specification=specification,
        context=interview_context(),
        behaviours_confirmed=True,
        confirmed=True,
    )
    specification.behaviour("EB-1").description += " with audit logs"  # type: ignore[union-attr]

    _reconcile_locks(working, before)

    assert not working.behaviours_confirmed
    assert not working.confirmed


def test_compile_specification_returns_both_yaml_strings_and_writes_nothing() -> None:
    result = compile_specification(research_assistant())

    assert result.specification_yaml.strip()
    assert "scenarios" in result.specification_yaml


def test_compile_specification_raises_on_a_specification_that_will_not_build() -> None:
    with pytest.raises(CompilationError):
        compile_specification(_empty_specification())
