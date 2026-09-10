from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from metis.api.routes.wizard import package as package_route
from tests.fixtures.wizard.profiles import research_assistant


def _profile() -> str:
    return research_assistant().model_dump_json()


def test_package_returns_a_portable_zip_with_profile_and_fixtures(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/wizard/package",
        data={"profile": _profile()},
        files=[("files", ("policy.pdf", b"policy bytes", "application/pdf"))],
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "experiment.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            "experiment.yaml",
            "profile.yaml",
            "fixtures/",
            "fixtures/policy.pdf",
        }
        assert archive.read("fixtures/policy.pdf") == b"policy bytes"


def test_package_includes_unreferenced_fixture_bytes_without_server_state(
    make_client,
) -> None:
    request = {
        "profile": _profile(),
    }
    files = [
        ("files", ("policy.pdf", b"policy bytes", "application/pdf")),
        ("files", ("notes.txt", b"notes", "text/plain")),
    ]

    first = make_client().post("/api/v1/wizard/package", data=request, files=files)
    second = make_client().post(
        "/api/v1/wizard/package",
        data=request,
        files=[("files", ("policy.pdf", b"policy bytes", "application/pdf"))],
    )

    assert first.status_code == second.status_code == 200
    with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
        assert archive.read("fixtures/notes.txt") == b"notes"
    with zipfile.ZipFile(io.BytesIO(second.content)) as archive:
        assert "fixtures/notes.txt" not in archive.namelist()


def test_package_rejects_a_profile_with_a_missing_fixture(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/wizard/package",
        data={"profile": _profile()},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "compilation_failed"
    assert "policy.pdf" in response.json()["message"]


def test_package_rejects_an_invalid_profile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wizard/package",
        data={"profile": "not json"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "type": "failure",
        "code": "validation_error",
        "message": "The submitted Profile is invalid.",
        "retryable": False,
    }


def test_package_rejects_unsafe_fixture_names(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wizard/package",
        data={"profile": _profile()},
        files=[("files", ("../policy.pdf", b"policy bytes", "application/pdf"))],
    )

    assert response.status_code == 400
    assert response.json()["code"] == "compilation_failed"


def test_package_rejects_duplicate_fixture_identities(client: TestClient) -> None:
    response = client.post(
        "/api/v1/wizard/package",
        data={"profile": _profile()},
        files=[
            ("files", ("policy.pdf", b"one", "application/pdf")),
            ("files", ("POLICY.PDF", b"two", "application/pdf")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["code"] == "compilation_failed"


def test_package_rejects_excess_fixture_parts_before_reading_bodies(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/wizard/package",
        data={"profile": _profile()},
        files=[
            ("files", (f"fixture-{index}.txt", b"x", "text/plain"))
            for index in range(21)
        ],
    )

    assert response.status_code == 400
    assert response.json()["code"] == "compilation_failed"


class CloseTrackingStream(io.BytesIO):
    """Track direct route cleanup without relying on multipart parser details."""

    def __init__(self, content: bytes, *, failure: BaseException | None = None) -> None:
        super().__init__(content)
        self.failure = failure
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self.failure is not None:
            raise self.failure
        return super().read(size)


def test_package_closes_uploads_after_success() -> None:
    stream = CloseTrackingStream(b"fixture")
    response = package_route(
        _profile(), [UploadFile(filename="policy.pdf", file=stream)]
    )

    assert response.status_code == 200
    assert stream.closed
    assert stream.read_sizes
    assert all(size > 0 for size in stream.read_sizes)


def test_package_closes_uploads_after_unexpected_failure() -> None:
    stream = CloseTrackingStream(b"fixture", failure=RuntimeError("read failed"))

    with pytest.raises(RuntimeError, match="read failed"):
        package_route(_profile(), [UploadFile(filename="policy.pdf", file=stream)])

    assert stream.closed
