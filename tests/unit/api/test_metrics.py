from __future__ import annotations

from fastapi.testclient import TestClient


def test_metric_catalogue_is_sorted_and_has_only_display_fields(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    rows = response.json()
    assert rows == sorted(rows, key=lambda row: row["fqn"])
    assert rows
    assert all(set(row) == {"fqn", "name", "description"} for row in rows)


def test_metric_catalogue_failure_uses_service_error_shape(
    client: TestClient,
    monkeypatch,
) -> None:
    import metis.api.routes.metrics as metrics_routes

    monkeypatch.setattr(
        metrics_routes,
        "metric_catalogue",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    response = client.get("/api/v1/metrics")

    assert response.status_code == 500
    assert response.json() == {
        "type": "failure",
        "code": "internal_error",
        "message": "The metric catalogue could not be loaded.",
        "retryable": False,
    }
