"""The Interview operation as a stateless transaction."""

from __future__ import annotations

import pytest
from fixtures.profiles import research_assistant
from fixtures.scripted import ScriptedInterviewer, ScriptedMatcher

from metis.wizard import (
    CompilationError,
    InterviewEndRequest,
    InterviewErrorCode,
    InterviewFailure,
    InterviewStartRequest,
    InterviewSuccess,
    InterviewTurnRequest,
    compile_profile,
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
    Option,
    OptionId,
    Product,
    ProductProfile,
)
from metis.wizard.contracts.interview_state import InterviewState
from metis.wizard.domain.permissions import InterviewStep


def _start(*, interviewer=None):
    return handle_interview(
        InterviewStartRequest(description="A research assistant"),
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


def _empty_profile() -> ProductProfile:
    return ProductProfile(product=Product(name="", description="", users=""))


def _pending_choice(request_id: str = "req-1") -> InterviewState:
    return InterviewState(
        profile=research_assistant(),
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
    assert result.state.pending is not None


def test_start_with_whitespace_is_rejected_before_processing() -> None:
    with pytest.raises(ValueError):
        InterviewStartRequest(description="  ")


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
    profile = research_assistant()
    profile.behaviour("EB-1").criteria = []  # type: ignore[union-attr]
    state = InterviewState(
        profile=profile,
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
    assert result.state.profile.behaviour("EB-1").criteria[0].metric_fqn is None  # type: ignore[union-attr]


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
    profile = research_assistant()
    pending = behaviours_screen(profile, "Review Behaviours")
    pending.request_id = "req-behaviours"
    pending.stage = InterviewStep.BEHAVIOURS
    state = InterviewState(profile=profile, pending=pending)

    result = _turn(
        state,
        ChoiceResponse(selected=["tick:EB-1", "continue"]),
    )

    assert isinstance(result, InterviewSuccess)
    assert result.stage is InterviewStep.BEHAVIOURS
    assert result.state.pending is not None
    assert result.state.pending.stage is InterviewStep.BEHAVIOURS
    assert not result.state.behaviours_confirmed
    assert not result.state.profile.behaviour("EB-1").measured  # type: ignore[union-attr]


class ClarifyUnavailable(ScriptedInterviewer):
    def clarify(self, profile, history, phase="product"):
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
    profile = research_assistant()
    profile.behaviour("EB-1").criteria[0].metric_fqn = None  # type: ignore[union-attr]
    result = _end(
        InterviewState(profile=profile, behaviours_confirmed=True),
        matcher=ScriptedMatcher(),
    )

    assert isinstance(result, InterviewSuccess)
    assert result.outcome == "done"
    assert result.state.confirmed
    assert result.state.pending is None
    assert result.state.profile.behaviour("EB-1").criteria[0].metric_fqn  # type: ignore[union-attr]


def test_final_continue_completes_a_ready_specification() -> None:
    profile = research_assistant()
    pending = scenarios_screen(profile, "Review scenarios")
    pending.request_id = "req-final"
    pending.stage = InterviewStep.SCENARIOS
    state = InterviewState(
        profile=profile,
        behaviours_confirmed=True,
        pending=pending,
    )

    result = _turn(state, ChoiceResponse(selected=["continue"]))

    assert isinstance(result, InterviewSuccess)
    assert result.outcome == "done"
    assert result.state.confirmed
    assert result.state.pending is None


def test_end_on_a_held_gate_preserves_state() -> None:
    profile = research_assistant()
    profile.scenarios = [s for s in profile.scenarios if s.id != "S-2"]
    state = InterviewState(profile=profile, behaviours_confirmed=True)

    result = _end(state)

    assert isinstance(result, InterviewFailure)
    assert result.code is InterviewErrorCode.COMPLETION_FAILED
    assert result.state == state
    assert any(gap.subject == "EB-3" for gap in result.missing)


def test_failed_end_preserves_pending_state_for_a_later_turn() -> None:
    class DraftUnavailable(ScriptedInterviewer):
        def draft_behaviours(self, profile, history):
            raise InterviewerOutputError("three attempts, all failed")

    state = InterviewState(
        profile=ProductProfile(
            product=Product(name="Tool", description="A tool", users="Analysts")
        ),
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
        profile=research_assistant(), behaviours_confirmed=True, confirmed=True
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
        (InterviewState(profile=_empty_profile()), InterviewStep.CLARIFY),
        (InterviewState(profile=research_assistant()), InterviewStep.BEHAVIOURS),
        (
            InterviewState(
                profile=research_assistant(), behaviours_confirmed=True, confirmed=True
            ),
            InterviewStep.DONE,
        ),
    ],
)
def test_derive_stage_reads_the_profile_top_to_bottom(
    state: InterviewState, expected: InterviewStep
) -> None:
    assert derive_stage(state) is expected


def test_criteria_precede_personas_when_a_measured_behaviour_lacks_them() -> None:
    profile = research_assistant()
    profile.behaviour("EB-1").criteria = []  # type: ignore[union-attr]
    state = InterviewState(profile=profile, behaviours_confirmed=True)

    assert derive_stage(state) is InterviewStep.CRITERIA


def test_behaviour_edit_clears_both_confirmation_locks() -> None:
    profile = research_assistant()
    before = profile.model_copy(deep=True)
    working = DriverState(
        step=InterviewStep.BEHAVIOURS,
        profile=profile,
        behaviours_confirmed=True,
        confirmed=True,
    )
    profile.behaviour("EB-1").description += " with audit logs"  # type: ignore[union-attr]

    _reconcile_locks(working, before)

    assert not working.behaviours_confirmed
    assert not working.confirmed


def test_compile_profile_returns_both_yaml_strings_and_writes_nothing() -> None:
    result = compile_profile(research_assistant())

    assert result.profile_yaml.strip()
    assert "scenarios" in result.experiment_yaml


def test_compile_profile_raises_on_a_profile_that_will_not_build() -> None:
    with pytest.raises(CompilationError):
        compile_profile(_empty_profile())
