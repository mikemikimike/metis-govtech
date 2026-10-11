from __future__ import annotations

from fastapi.testclient import TestClient


def test_grader_catalogue_is_sorted_and_has_only_display_fields(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/graders")

    assert response.status_code == 200
    rows = response.json()
    assert rows == sorted(rows, key=lambda row: row["fqn"])
    assert rows
    assert all(set(row) == {"fqn", "name", "description"} for row in rows)


def test_grader_catalogue_failure_uses_service_error_shape(
    client: TestClient,
    monkeypatch,
) -> None:
    import metis.api.routes.graders as graders_routes

    monkeypatch.setattr(
        graders_routes,
        "grader_catalogue",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    response = client.get("/api/v1/graders")

    assert response.status_code == 500
    assert response.json() == {
        "type": "failure",
        "code": "internal_error",
        "message": "The grader catalogue could not be loaded.",
        "retryable": False,
    }
