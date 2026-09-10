from __future__ import annotations

from fastapi.testclient import TestClient


def test_wizard_config_returns_package_owned_working_status(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/wizard/config")

    assert response.status_code == 200
    body = response.json()
    assert (
        body["opening_question"]
        == "Tell me about your product — what it does and who it's for."
    )
    assert body["working_status"] == "Working on your Interview…"
    assert [item["id"] for item in body["perspectives"]] == [
        "end_user",
        "engineer",
        "compliance",
        "security",
    ]
    assert all(item["label"] and item["question"] for item in body["perspectives"])
