"""The client-held interview state: what it carries, and what survives the wire.

`InterviewState` is a plain value the client owns between turns. It is never written to a file by
the package and never carries a transcript or a stage — a stateless HTTP server and the CLI both
serialize it to JSON and send it back on the next turn. These tests fix that value contract: the
field set, and that a pending screen rehydrates as its own concrete subclass across a round trip.
"""

import pytest

from metis.wizard.contracts import (
    ChatRequest,
    ChoiceRequest,
    FormField,
    FormRequest,
    InterviewContext,
    Option,
    OptionId,
    Perspective,
    Turn,
)
from metis.wizard.contracts.interview_state import InterviewState
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.profiles import research_assistant


def _roundtrip(state: InterviewState) -> InterviewState:
    """Serialize to JSON and back, exactly as a client holds the state between turns."""
    return InterviewState.model_validate_json(state.model_dump_json())


def test_pending_state_requires_request_identity_and_stage() -> None:
    with pytest.raises(ValueError, match="pending.request_id"):
        InterviewState(
            profile=research_assistant(),
            pending=ChoiceRequest(
                prompt="Do these look right?",
                options=[Option(id=OptionId(action="accept"), label="Looks right")],
                stage=InterviewStep.BEHAVIOURS,
            ),
        )

    required = ChoiceRequest.model_json_schema()["required"]
    assert "request_id" in required
    assert "stage" in required
    request_schema = ChoiceRequest.model_json_schema()["properties"]["request_id"]
    stage_schema = ChoiceRequest.model_json_schema()["properties"]["stage"]
    assert request_schema == {"type": "string"}
    assert stage_schema == {"$ref": "#/$defs/InterviewStep"}

    with pytest.raises(ValueError, match="pending.stage"):
        InterviewState(
            profile=research_assistant(),
            pending=ChoiceRequest(
                prompt="Do these look right?",
                options=[],
                request_id="req-1",
                stage=None,
            ),
        )


def test_the_state_carries_only_client_held_control_data() -> None:
    """No id, no stage, no resolved-request transcript — only what the next turn needs.

    The stage is derived and the client never stores it; there is no persisted request log. This
    field set is an architectural constraint, so it is asserted directly rather than by behaviour.
    """
    assert set(InterviewState.model_fields) == {
        "profile",
        "context",
        "behaviours_confirmed",
        "confirmed",
        "history",
        "user_typed",
        "issued_ids",
        "pending",
    }


def test_context_defaults_to_the_end_user_perspective() -> None:
    state = InterviewState(profile=research_assistant())

    assert state.context == InterviewContext(perspective=Perspective.END_USER)


def test_context_round_trips_without_entering_the_profile() -> None:
    state = InterviewState(
        profile=research_assistant(),
        context=InterviewContext(perspective=Perspective.SECURITY),
    )

    loaded = _roundtrip(state)

    assert loaded.context.perspective is Perspective.SECURITY
    assert "perspective" not in loaded.profile.model_dump()


def test_state_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        InterviewState.model_validate(
            {
                "profile": research_assistant().model_dump(),
                "unexpected": True,
            }
        )


def test_history_is_bounded_to_the_model_context_limit() -> None:
    with pytest.raises(ValueError):
        InterviewState(
            profile=research_assistant(),
            history=[Turn(role="user", text=str(index)) for index in range(13)],
        )


def test_a_pending_choice_screen_rehydrates_as_its_subclass() -> None:
    """`Literal` discriminators exist so JSON rebuilds the concrete request, not the base."""
    state = InterviewState(
        profile=research_assistant(),
        pending=ChoiceRequest(
            prompt="Do these look right?",
            options=[Option(id=OptionId(action="accept"), label="Looks right")],
            request_id="req-1",
            stage=InterviewStep.BEHAVIOURS,
        ),
    )

    loaded = _roundtrip(state)

    assert isinstance(loaded.pending, ChoiceRequest)
    assert loaded.pending.options[0].label == "Looks right"
    assert loaded.pending.options[0].id.action == "accept"


def test_a_targeted_follow_up_keeps_its_target_across_the_wire() -> None:
    """A per-card chat or manual criterion scopes its follow-up to one behaviour by id.

    If a round trip dropped `target`, a targeted edit would silently widen into a screen-wide one,
    so the scope must survive serialization for both typed request shapes.
    """
    for request in (
        ChatRequest(
            prompt="What would you like to change about EB-2?",
            target="EB-2",
            request_id="req-chat",
            stage=InterviewStep.CRITERIA,
        ),
        FormRequest(
            prompt="Write one yourself.",
            target="EB-2",
            fields=[FormField(id="given", label="Given")],
            request_id="req-form",
            stage=InterviewStep.CRITERIA,
        ),
    ):
        loaded = _roundtrip(
            InterviewState(profile=research_assistant(), pending=request)
        )

        assert type(loaded.pending) is type(request)
        assert loaded.pending is not None
        assert loaded.pending.target == "EB-2"
