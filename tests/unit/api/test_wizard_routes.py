"""The HTTP adapter for the Interview lifecycle and compilation."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from metis.api.main import create_app
from metis.api.routes import wizard as wizard_routes
from metis.wizard.application.interviewer import InterviewerOutputError
from metis.wizard.contracts import (
    ChatRequest,
    ChatResponse,
    InterviewEndRequest,
    InterviewStartRequest,
    InterviewState,
    InterviewTurnRequest,
    Perspective,
    ProductProfile,
)
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.profiles import research_assistant
from tests.fixtures.wizard.scripted import ScriptedInterviewer


def _start_body() -> dict[str, object]:
    return InterviewStartRequest(description="A policy research assistant").model_dump(
        mode="json"
    )


def _empty_profile() -> dict[str, object]:
    return ProductProfile.model_validate(
        {"product": {"name": "", "description": "", "users": ""}}
    ).model_dump(mode="json")


def _pending_state() -> InterviewState:
    return InterviewState(
        profile=research_assistant(),
        behaviours_confirmed=True,
        pending=ChatRequest(
            prompt="What should change?",
            request_id="req-1",
            stage=InterviewStep.CRITERIA,
        ),
    )


def test_start_returns_state_with_a_pending_request(client: TestClient) -> None:
    response = client.post("/api/v1/wizard/interview/start", json=_start_body())

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "success"
    assert body["outcome"] == "awaiting_response"
    assert body["state"]["pending"]["request_id"]
    assert body["state"]["context"]["perspective"] == "end_user"


def test_start_records_the_chosen_perspective(client: TestClient) -> None:
    body = {
        "description": "A policy research assistant",
        "perspective": Perspective.SECURITY.value,
    }

    response = client.post("/api/v1/wizard/interview/start", json=body)

    assert response.status_code == 200
    assert response.json()["state"]["context"]["perspective"] == "security"


def test_a_stale_request_id_is_a_400_with_the_state_echoed_back(
    client: TestClient,
) -> None:
    opening = client.post("/api/v1/wizard/interview/start", json=_start_body()).json()
    state = opening["state"]
    body = {
        "state": state,
        "request_id": "not-the-pending-id",
        "response": ChatResponse(text="hi").model_dump(mode="json"),
    }

    response = client.post("/api/v1/wizard/interview/turn", json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "request_id_mismatch"
    assert response.json()["state"] == state


def test_a_body_that_breaks_the_schema_is_a_422_in_the_service_error_shape(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/wizard/interview/start", json={})

    assert response.status_code == 422
    assert response.json()["type"] == "failure"
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("field", ["request_id", "stage"])
@pytest.mark.parametrize(
    "value", [pytest.param(None, id="null"), pytest.param("missing")]
)
def test_pending_request_metadata_is_required_and_non_null_over_http(
    client: TestClient, field: str, value: object
) -> None:
    opening = client.post("/api/v1/wizard/interview/start", json=_start_body()).json()
    state = deepcopy(opening["state"])
    if value == "missing":
        state["pending"].pop(field)
    else:
        state["pending"][field] = value
    body = {
        "state": state,
        "request_id": "req-1",
        "response": ChatResponse(text="a policy tool").model_dump(mode="json"),
    }

    response = client.post("/api/v1/wizard/interview/turn", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_an_exhausted_model_is_a_503_retryable_failure(make_client) -> None:
    class ClarifyUnavailable(ScriptedInterviewer):
        def clarify(self, profile, history, phase="product", context=None):
            raise InterviewerOutputError("three attempts, all failed")

    client = make_client(ClarifyUnavailable())
    response = client.post("/api/v1/wizard/interview/start", json=_start_body())

    assert response.status_code == 503
    assert response.json()["code"] == "model_unavailable"
    assert response.json()["retryable"] is True
    assert response.json()["state"] is None


def test_an_exhausted_model_during_turn_is_a_503_with_safe_state(make_client) -> None:
    class ClarifyUnavailable(ScriptedInterviewer):
        def clarify(self, profile, history, phase="product", context=None):
            raise InterviewerOutputError("three attempts, all failed")

    opening = (
        make_client().post("/api/v1/wizard/interview/start", json=_start_body()).json()
    )
    state = opening["state"]
    response = make_client(ClarifyUnavailable()).post(
        "/api/v1/wizard/interview/turn",
        json={
            "state": state,
            "request_id": state["pending"]["request_id"],
            "response": ChatResponse(text="It answers policy questions.").model_dump(
                mode="json"
            ),
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "model_unavailable"
    assert response.json()["state"] == state


def test_an_exhausted_model_during_end_is_a_503_with_safe_state(make_client) -> None:
    class DraftUnavailable(ScriptedInterviewer):
        def draft_behaviours(self, profile, history, context=None):
            raise InterviewerOutputError("three attempts, all failed")

    state = InterviewState(
        profile=ProductProfile.model_validate(
            {
                "product": {
                    "name": "Policy helper",
                    "description": "Answers policy questions",
                    "users": "Policy analysts",
                }
            }
        )
    )
    response = make_client(DraftUnavailable()).post(
        "/api/v1/wizard/interview/end",
        json=InterviewEndRequest(state=state).model_dump(mode="json"),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "model_unavailable"
    assert response.json()["state"] == state.model_dump(mode="json")


def test_an_unexpected_interview_fault_is_a_stable_500_failure(make_client) -> None:
    class BrokenInterviewer(ScriptedInterviewer):
        def clarify(self, profile, history, phase="product", context=None):
            raise RuntimeError("unexpected provider bug")

    client = make_client(BrokenInterviewer())
    response = client.post("/api/v1/wizard/interview/start", json=_start_body())

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert response.json()["retryable"] is False


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/wizard/interview/start", _start_body()),
        (
            "/api/v1/wizard/interview/turn",
            InterviewTurnRequest(
                state=_pending_state(),
                request_id="req-1",
                response=ChatResponse(text="Make it clearer."),
            ).model_dump(mode="json"),
        ),
        (
            "/api/v1/wizard/interview/end",
            InterviewEndRequest(state=_pending_state()).model_dump(mode="json"),
        ),
    ],
)
def test_unexpected_interview_service_faults_are_stable_500_responses(
    path: str, body: dict[str, object]
) -> None:
    def fail(_request):
        raise RuntimeError("unexpected service fault")

    client = TestClient(
        create_app(interview_handler=fail), raise_server_exceptions=False
    )

    response = client.post(path, json=body)

    assert response.status_code == 500
    assert response.json() == {
        "type": "failure",
        "code": "internal_error",
        "message": "The API could not complete the request.",
        "retryable": False,
    }


def test_end_returns_best_effort_completion(client: TestClient) -> None:
    state = {
        "profile": research_assistant().model_dump(mode="json"),
        "behaviours_confirmed": True,
        "confirmed": False,
        "history": [],
        "user_typed": [],
        "issued_ids": [],
        "pending": None,
    }

    response = client.post("/api/v1/wizard/interview/end", json={"state": state})

    assert response.status_code == 200
    assert response.json()["outcome"] == "done"


def test_compile_returns_the_two_file_named_yaml_strings(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wizard/compile",
        json=research_assistant().model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"profile.yaml", "experiment.yaml"}
    assert body["profile.yaml"].strip()
    assert "scenarios" in body["experiment.yaml"]


def test_a_profile_that_will_not_build_is_a_400_compilation_failure(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/wizard/compile", json=_empty_profile())

    assert response.status_code == 400
    assert response.json()["code"] == "compilation_failed"


def test_an_unexpected_compile_fault_is_a_stable_500_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_profile):
        raise RuntimeError("unexpected compiler fault")

    monkeypatch.setattr(wizard_routes, "compile_profile", fail)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/v1/wizard/compile",
        json=research_assistant().model_dump(mode="json"),
    )

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
