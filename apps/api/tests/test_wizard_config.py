from __future__ import annotations

from fastapi.testclient import TestClient


def test_wizard_config_returns_package_owned_working_status(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/wizard/config")

    assert response.status_code == 200
    assert response.json() == {"working_status": "Working on your Interview…"}
