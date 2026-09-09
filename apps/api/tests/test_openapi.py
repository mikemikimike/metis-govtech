"""The generated OpenAPI document for the versioned Interview lifecycle."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_the_route_table_is_exactly_health_interview_lifecycle_compile_and_package(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/health",
        "/api/v1/metrics",
        "/api/v1/wizard/config",
        "/api/v1/wizard/package",
        "/api/v1/wizard/interview/start",
        "/api/v1/wizard/interview/turn",
        "/api/v1/wizard/interview/end",
        "/api/v1/wizard/compile",
    }


def test_metric_route_documents_success_and_internal_error(client: TestClient) -> None:
    responses = client.get("/openapi.json").json()["paths"]["/api/v1/metrics"]["get"][
        "responses"
    ]
    assert {"200", "500"} <= set(responses)


def test_each_interview_route_documents_its_service_statuses(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/wizard/interview/start",
        "/api/v1/wizard/interview/turn",
        "/api/v1/wizard/interview/end",
    ):
        responses = paths[path]["post"]["responses"]
        assert {"200", "400", "422", "500", "503"}.issubset(responses)

    compile_responses = paths["/api/v1/wizard/compile"]["post"]["responses"]
    assert {"200", "400", "422", "500"}.issubset(compile_responses)


def test_concrete_request_models_have_flat_required_fields(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    start = schemas["InterviewStartRequest"]
    assert start["required"] == ["description"]
    assert start["additionalProperties"] is False

    turn = schemas["InterviewTurnRequest"]
    assert set(turn["required"]) == {"state", "request_id", "response"}
    assert turn["additionalProperties"] is False

    end = schemas["InterviewEndRequest"]
    assert end["required"] == ["state"]
    assert end["additionalProperties"] is False


def test_response_union_is_discriminated_by_result_type(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    result = paths["/api/v1/wizard/interview/turn"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert result["discriminator"]["propertyName"] == "type"
    assert set(result["discriminator"]["mapping"]) == {"success", "failure"}


def test_turn_response_body_is_discriminated_by_typed_response_kind(
    client: TestClient,
) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    response = schemas["InterviewTurnRequest"]["properties"]["response"]

    assert response["discriminator"]["propertyName"] == "type"
    assert set(response["discriminator"]["mapping"]) == {
        "chat",
        "choice",
        "form",
    }


def test_state_schema_bounds_history_and_requires_non_null_pending_metadata(
    client: TestClient,
) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert schemas["InterviewState"]["properties"]["history"]["maxItems"] == 12
    for name in ("ChatRequest", "ChoiceRequest", "FormRequest"):
        request = schemas[name]
        assert {"request_id", "stage"} <= set(request["required"])
        assert request["properties"]["request_id"] == {"type": "string"}
        assert request["properties"]["stage"] == {
            "$ref": "#/components/schemas/InterviewStep"
        }
