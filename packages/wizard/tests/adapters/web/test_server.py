"""The web door, driven the way a browser drives it.

The claim under test is not "the routes return 200". It is that the web door and the CLI door
reach the same place from the same answers — because they are the same two lines, and the only
thing either one implements is how to draw a screen.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fixtures.profiles import research_assistant
from fixtures.scripted import ScriptedInterviewer

from metis.wizard.application import Session, SessionState
from metis.wizard.contracts import ChoiceResponse
from metis.wizard.domain.permissions import SessionStep

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from metis.wizard.adapters.web.server import (  # noqa: E402
    _response_adapter,
    create_app,
)
from metis.wizard.adapters.web.store import UNTITLED, SessionStore  # noqa: E402


def client(root: Path) -> TestClient:
    return TestClient(create_app(interviewer_factory=ScriptedInterviewer, root=root))


def _seed(root: Path, name: str, *, step=SessionStep.PERSONAS) -> SessionState:
    """A session on disk in the layout `--out-dir` produces."""
    state = SessionState(id=name, profile=research_assistant(), step=step)
    state.save(root / name / "session.json")
    return state


# ── the session list ───────────────────────────────────────────────────────


def test_an_empty_root_lists_nothing(tmp_path: Path) -> None:
    assert client(tmp_path).get("/api/sessions").json() == []


def test_sessions_are_listed_with_their_product_name(tmp_path: Path) -> None:
    _seed(tmp_path, "wizard-aaa")

    rows = client(tmp_path).get("/api/sessions").json()

    assert [r["id"] for r in rows] == ["wizard-aaa"]
    assert rows[0]["title"] == "Research assistant"
    assert rows[0]["step"] == "personas"


def test_a_session_without_a_product_name_is_still_listed(tmp_path: Path) -> None:
    from metis.wizard.contracts import Product, ProductProfile

    state = SessionState(
        id="wizard-bbb",
        profile=ProductProfile(product=Product(name="", summary="", users="")),
    )
    state.save(tmp_path / "wizard-bbb" / "session.json")

    rows = client(tmp_path).get("/api/sessions").json()

    assert rows[0]["title"] == UNTITLED


def test_an_unreadable_session_does_not_take_the_list_down(tmp_path: Path) -> None:
    """One session written by an older wizard should cost you that session, not all of them."""
    _seed(tmp_path, "wizard-good")
    (tmp_path / "wizard-old").mkdir()
    (tmp_path / "wizard-old" / "session.json").write_text("{ not json")

    rows = client(tmp_path).get("/api/sessions").json()

    assert [r["id"] for r in rows] == ["wizard-good"]


# ── the payload ────────────────────────────────────────────────────────────


def test_one_payload_serves_all_three_panes(tmp_path: Path) -> None:
    _seed(tmp_path, "wizard-ccc")

    body = client(tmp_path).get("/api/sessions/wizard-ccc").json()

    assert set(body) == {
        "id",
        "step",
        "busy_message",
        "done",
        "requests",
        "profile",
    }
    assert body["requests"], "the live screen is in the list"
    assert body["requests"][-1]["state"] == "pending"
    assert body["profile"]["product"]["name"] == "Research assistant"
    assert body["busy_message"] == "Building coverage scenarios…"


def test_scenario_card_run_count_survives_the_http_wire(tmp_path: Path) -> None:
    _seed(tmp_path, "wizard-runs", step=SessionStep.SCENARIOS)

    body = client(tmp_path).get("/api/sessions/wizard-runs").json()
    scenario_card = next(
        card for card in body["requests"][-1]["cards"] if card["id"] == "S-1"
    )

    assert scenario_card["kind"] == "scenario"
    assert scenario_card["runs"] == 6


def test_an_unknown_session_is_a_404(tmp_path: Path) -> None:
    assert client(tmp_path).get("/api/sessions/nope").status_code == 404


def test_a_new_session_starts_at_clarify(tmp_path: Path) -> None:
    body = client(tmp_path).post("/api/sessions").json()

    assert body["step"] == "clarify"
    assert body["profile"]["product"]["name"] == ""
    assert (tmp_path / body["id"] / "session.json").is_file()


# ── the two doors agree ────────────────────────────────────────────────────


def test_the_web_door_reaches_the_same_state_as_the_cli(tmp_path: Path) -> None:
    """The same two answers, through HTTP and through the object, land in the same place."""
    web_root = tmp_path / "web"
    cli_root = tmp_path / "cli"
    _seed(web_root, "s", step=SessionStep.BEHAVIOURS)
    _seed(cli_root, "s", step=SessionStep.BEHAVIOURS)

    answers = [["accept"], ["tick:EB-2"]]

    api = client(web_root)
    api.get("/api/sessions/s")
    for selected in answers:
        api.post(
            "/api/sessions/s/respond", json={"type": "choice", "selected": selected}
        )

    from metis.wizard.application.driver import StepDriver

    cli = Session.resume(
        cli_root / "s" / "session.json",
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )
    for selected in answers:
        cli.next()
        cli.respond(ChoiceResponse(selected=selected))
    cli.next()

    web = SessionStore(web_root).load("s")
    assert web is not None
    assert web.step is cli.state.step
    assert web.profile == cli.state.profile
    assert [r.state for r in web.requests] == [r.state for r in cli.state.requests]


def _both_doors_through(tmp_path: Path, responses: list[dict], *, step) -> None:
    """Run the same responses through the HTTP door and the object door, and assert they land
    on the same profile, step and receipt states. Each `response` is the JSON body a browser
    would post; the CLI runs the pydantic-validated equivalent through the same driver."""
    from metis.wizard.application.driver import StepDriver

    web_root = tmp_path / "web"
    cli_root = tmp_path / "cli"
    _seed(web_root, "s", step=step)
    _seed(cli_root, "s", step=step)

    api = client(web_root)
    api.get("/api/sessions/s")
    for body in responses:
        api.post("/api/sessions/s/respond", json=body)

    cli = Session.resume(
        cli_root / "s" / "session.json",
        driver=StepDriver(interviewer=ScriptedInterviewer()),
    )
    for body in responses:
        cli.next()
        cli.respond(_response_adapter.validate_python(body))
    cli.next()

    web = SessionStore(web_root).load("s")
    assert web is not None
    assert web.step is cli.state.step
    assert web.profile == cli.state.profile
    assert [r.state for r in web.requests] == [r.state for r in cli.state.requests]


def test_the_two_doors_agree_on_a_targeted_criterion_workflow(tmp_path: Path) -> None:
    """ "Write one myself" — select, then submit the Given/When/Then form — appends the same
    FORM criterion through either door, target carried across the choice→form round trip."""
    _both_doors_through(
        tmp_path,
        [
            {"type": "choice", "selected": ["type:EB-1"]},
            {
                "type": "form",
                "values": {
                    "given": "a long report",
                    "when": "asked to summarise",
                    "then": "citations kept",
                },
            },
        ],
        step=SessionStep.CRITERIA,
    )
    web = SessionStore(tmp_path / "web").load("s")
    assert web is not None
    fresh = web.profile.behaviour("EB-1").criteria[-1]  # type: ignore[union-attr]
    assert (fresh.id, fresh.given, fresh.is_user_typed) == (
        "AC-1-3",
        "a long report",
        True,
    )


def test_the_two_doors_agree_on_typed_scenario_field_edits(tmp_path: Path) -> None:
    _both_doors_through(
        tmp_path,
        [
            {"type": "choice", "values": {"trials:S-2": 7}},
            {
                "type": "choice",
                "values": {"files:S-2": [" policy.pdf ", "faq.md"]},
            },
        ],
        step=SessionStep.SCENARIOS,
    )

    web = SessionStore(tmp_path / "web").load("s")
    assert web is not None
    scenario = web.profile.scenario("S-2")
    assert scenario is not None
    assert (scenario.num_trials, scenario.fixtures) == (7, ["policy.pdf", "faq.md"])
    assert web.pending is not None
    assert "Total: 13 runs" in web.pending.footer  # type: ignore[union-attr]
    scenario_card = next(card for card in web.pending.cards if card.id == "S-2")  # type: ignore[union-attr]
    assert scenario_card.runs == 7


def test_a_session_made_in_the_browser_is_resumable_from_the_terminal(
    tmp_path: Path,
) -> None:
    """The layout is the one `--out-dir` already means, so neither door converts anything."""
    from metis.wizard.adapters.cli.commands import _session_path

    created = client(tmp_path).post("/api/sessions").json()

    out_dir = tmp_path / created["id"]
    assert _session_path(out_dir).is_file()
    assert Session.resume(_session_path(out_dir)).state.id == created["id"]


def test_a_session_made_in_the_terminal_appears_in_the_browser(tmp_path: Path) -> None:
    """The CLI's default writes straight into the out-dir rather than a subdirectory."""
    SessionState(id="wizard-cli", profile=research_assistant()).save(
        tmp_path / "session.json"
    )

    rows = client(tmp_path).get("/api/sessions").json()

    assert [r["id"] for r in rows] == ["wizard-cli"]


def test_nothing_is_held_between_requests(tmp_path: Path) -> None:
    """Each call loads, applies one response and saves — so a fresh app sees the same thing."""
    _seed(tmp_path, "wizard-ddd", step=SessionStep.BEHAVIOURS)

    first = client(tmp_path)
    first.get("/api/sessions/wizard-ddd")
    first.post(
        "/api/sessions/wizard-ddd/respond",
        json={"type": "choice", "selected": ["accept"]},
    )

    # A different app object entirely, sharing only the directory.
    body = client(tmp_path).get("/api/sessions/wizard-ddd").json()

    assert body["step"] == "prioritise"
    assert body["requests"][0]["state"] == "resolved"


def test_answering_a_finished_interview_is_refused(tmp_path: Path) -> None:
    """A door that kept a stale screen on screen would otherwise post into a closed session."""
    _seed(tmp_path, "wizard-eee", step=SessionStep.DONE)
    api = client(tmp_path)

    assert api.get("/api/sessions/wizard-eee").json()["done"] is True

    refused = api.post(
        "/api/sessions/wizard-eee/respond",
        json={"type": "choice", "selected": ["accept"]},
    )

    assert refused.status_code == 409


# ── output ─────────────────────────────────────────────────────────────────


def test_the_experiment_can_be_downloaded(tmp_path: Path) -> None:
    _seed(tmp_path, "wizard-fff", step=SessionStep.DONE)

    response = client(tmp_path).get("/api/sessions/wizard-fff/experiment.yaml")

    assert response.status_code == 200
    assert "scenarios:" in response.text


def test_session_fixture_upload_lists_metadata_and_keeps_bytes_out_of_session_json(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "wizard-fixtures")
    upload = client(tmp_path).post(
        "/api/sessions/wizard-fixtures/fixtures",
        files=[("files", ("policy.pdf", b"pdf bytes", "application/pdf"))],
    )

    assert upload.status_code == 200
    assert upload.json()["added"] == [{"name": "policy.pdf", "size": 9}]
    assert client(tmp_path).get("/api/sessions/wizard-fixtures/fixtures").json() == [
        {"name": "policy.pdf", "size": 9}
    ]
    session_json = (tmp_path / "wizard-fixtures" / "session.json").read_text()
    assert "pdf bytes" not in session_json
    assert (
        tmp_path / "wizard-fixtures" / "fixtures" / "policy.pdf"
    ).read_bytes() == b"pdf bytes"


def test_engine_example_csv_fixture_uploads_without_transformation(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "wizard-example-csv")
    source = (
        Path(__file__).resolve().parents[5]
        / "packages/engine/example-experiment/fixtures/q3_sales.csv"
    )

    with source.open("rb") as fixture:
        response = client(tmp_path).post(
            "/api/sessions/wizard-example-csv/fixtures",
            files=[("files", (source.name, fixture, "text/csv"))],
        )

    assert response.status_code == 200
    stored = tmp_path / "wizard-example-csv" / "fixtures" / source.name
    assert stored.read_bytes() == source.read_bytes()


def test_fixture_upload_batches_are_all_or_nothing(tmp_path: Path) -> None:
    _seed(tmp_path, "wizard-batch")
    response = client(tmp_path).post(
        "/api/sessions/wizard-batch/fixtures",
        files=[
            ("files", ("good.txt", b"good", "text/plain")),
            ("files", ("bad.exe", b"bad", "application/octet-stream")),
        ],
    )

    assert response.status_code == 422
    assert client(tmp_path).get("/api/sessions/wizard-batch/fixtures").json() == []


def test_referenced_fixture_cannot_be_deleted_but_unreferenced_can(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "wizard-delete")
    api = client(tmp_path)
    api.post(
        "/api/sessions/wizard-delete/fixtures",
        files=[
            ("files", ("policy.pdf", b"policy", "application/pdf")),
            ("files", ("notes.txt", b"notes", "text/plain")),
        ],
    )

    assert (
        api.delete("/api/sessions/wizard-delete/fixtures/policy.pdf").status_code == 409
    )
    assert (
        api.delete("/api/sessions/wizard-delete/fixtures/notes.txt").status_code == 200
    )
    assert [
        row["name"] for row in api.get("/api/sessions/wizard-delete/fixtures").json()
    ] == ["policy.pdf"]


def test_interview_bundle_download_has_the_engine_layout(tmp_path: Path) -> None:
    _seed(tmp_path, "wizard-zip", step=SessionStep.DONE)
    api = client(tmp_path)
    api.post(
        "/api/sessions/wizard-zip/fixtures",
        files=[("files", ("policy.pdf", b"policy", "application/pdf"))],
    )

    response = api.get("/api/sessions/wizard-zip/experiment.zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "experiment.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "experiment.yaml" in archive.namelist()
        assert "fixtures/policy.pdf" in archive.namelist()
    assert not (tmp_path / "wizard-zip" / "experiment.zip").exists()


def test_manual_bundle_route_is_stateless_and_includes_uploaded_files(
    tmp_path: Path,
) -> None:
    response = client(tmp_path).post(
        "/api/experiment.zip",
        data={"document": json.dumps(VALID_DOC)},
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("fixtures/data.csv") == b"a,b\n1,2\n"
    assert client(tmp_path).get("/api/sessions").json() == []
    assert list(tmp_path.iterdir()) == []


def test_manual_bundle_route_refuses_a_missing_referenced_file(tmp_path: Path) -> None:
    import copy

    document = copy.deepcopy(VALID_DOC)
    document["scenarios"][0]["fixtures"] = ["missing.txt"]
    response = client(tmp_path).post(
        "/api/experiment.zip", data={"document": json.dumps(document)}
    )

    assert response.status_code == 422
    assert "missing.txt" in response.text
    assert list(tmp_path.iterdir()) == []


# ── the metric catalogue ─────────────────────────────────────────────────────


def test_the_catalogue_route_serves_every_metric(tmp_path: Path) -> None:
    """The picker offers exactly what the catalogue reader knows, as one flat list."""
    from metis.wizard.application.matching.library_catalogue import library_catalogue

    rows = client(tmp_path).get("/api/metrics").json()

    assert {r["fqn"] for r in rows} == {s.fqn for s in library_catalogue()}
    first = rows[0]
    assert set(first) >= {"fqn", "name", "description"}
    # Flat FQNs after the library restructure: no module segment to group on.
    assert all(r["fqn"].startswith("metis.library.metrics.") for r in rows)


# ── authoring an experiment without an interview ─────────────────────────────

VALID_DOC = {
    "id": "hand-authored",
    "description": "An experiment typed in directly.",
    "personas": [{"id": "analyst", "description": "A policy analyst."}],
    "scenarios": [
        {
            "id": "S-1",
            "description": "Ask a question the library covers.",
            "num_trials": 3,
            "persona_refs": ["analyst"],
            "metric_refs": [],
        }
    ],
}


def test_a_submitted_document_compiles_to_a_downloadable_file(tmp_path: Path) -> None:
    import yaml

    response = client(tmp_path).post("/api/experiment.yaml", json=VALID_DOC)

    assert response.status_code == 200
    parsed = yaml.safe_load(response.text)
    assert parsed["id"] == "hand-authored"
    assert parsed["schema_version"] == 1  # stamped by the server, not supplied
    assert [t["id"] for t in parsed["scenarios"]] == ["S-1"]


def test_a_submitted_document_serialises_like_an_interviewed_one(
    tmp_path: Path,
) -> None:
    """Both doors route through the same serialiser, so identical content is byte-identical."""
    from metis.wizard.application.compile import compile_experiment, to_yaml
    from metis.wizard.contracts import Persona, Product, ProductProfile, Scenario

    profile = ProductProfile(
        product=Product(name="X", summary="the same description", users=""),
        personas=[Persona(id="analyst", description="A policy analyst.")],
        scenarios=[
            Scenario(
                id="S-1",
                description="Ask a question.",
                persona_refs=["analyst"],
                num_trials=3,
            )
        ],
    )
    interviewed = to_yaml(compile_experiment(profile, "same-id"))

    body = {
        "id": "same-id",
        "description": "the same description",
        "personas": [{"id": "analyst", "description": "A policy analyst."}],
        "scenarios": [
            {
                "id": "S-1",
                "description": "Ask a question.",
                "num_trials": 3,
                "persona_refs": ["analyst"],
                "metric_refs": [],
            }
        ],
    }
    response = client(tmp_path).post("/api/experiment.yaml", json=body)

    assert response.text == interviewed


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: d.update(id=""), "a blank id"),
        (lambda d: d.update(description=""), "a blank description"),
        (lambda d: d.update(personas=[]), "no personas"),
        (lambda d: d.update(scenarios=[]), "no scenarios"),
        (
            lambda d: d["scenarios"][0].update(persona_refs=[]),
            "a scenario with no persona",
        ),
    ],
)
def test_an_invalid_document_is_refused_with_no_file(
    tmp_path: Path, mutate, why: str
) -> None:
    """Each mandatory rule the schema enforces produces a rejection, not a file."""
    import copy

    doc = copy.deepcopy(VALID_DOC)
    mutate(doc)

    response = client(tmp_path).post("/api/experiment.yaml", json=doc)

    assert response.status_code == 422, why
    assert "schema_version" not in response.text  # no document leaked in the error


def test_authoring_writes_nothing_to_the_store(tmp_path: Path) -> None:
    """The route is stateless — a round trip leaves the session directory empty."""
    client(tmp_path).post("/api/experiment.yaml", json=VALID_DOC)

    assert client(tmp_path).get("/api/sessions").json() == []
    assert not any(tmp_path.iterdir())
