"""The web door.

The same two lines every door runs, taken one turn at a time. A browser cannot hold a
conversation in a process variable between requests, so each one loads the session, applies at
most one response, and saves — which is the arrangement `SessionState` was split out for.

Nothing here composes a sentence about the domain. The payload carries the requests the
package composed and the profile it built; the words are all already in them.
"""

from __future__ import annotations

import inspect
import json
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter
from starlette.background import BackgroundTask

from metis.wizard.adapters.web.store import SessionStore
from metis.wizard.application import Session, SessionVersionError
from metis.wizard.application.compile import (
    CompilationError,
    SpecificationError,
    build_experiment_document,
    compile_experiment,
    temporary_specification_directory,
    to_yaml,
    write_specification,
)
from metis.wizard.application.fixtures import FixtureError, FixtureLibrary
from metis.wizard.application.interviewer import Interviewer, InterviewerUnavailable
from metis.wizard.contracts.conversation import AnyResponse

if TYPE_CHECKING:
    from collections.abc import Callable

    from metis.wizard.application.driver import StepDriver
    from metis.wizard.application.matching.matcher import Embedder

_response_adapter: TypeAdapter[AnyResponse] = TypeAdapter(AnyResponse)

STATIC_DIR = Path(__file__).parent / "static"


def _fixture_library(path: Path) -> FixtureLibrary:
    return FixtureLibrary(path.parent / "fixtures")


def _profile_fixture_names(session: Session) -> list[str]:
    return [
        name for scenario in session.profile().scenarios for name in scenario.fixtures
    ]


def _cleanup_directory(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _specification_response(path: Path, *, cleanup: Path | None = None) -> FileResponse:
    background = (
        BackgroundTask(_cleanup_directory, cleanup) if cleanup is not None else None
    )
    return FileResponse(
        path,
        media_type="application/zip",
        filename="experiment.zip",
        background=background,
    )


def _submitted_document(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the hand-authoring presence rules shared by YAML and ZIP routes."""

    experiment_id = str(payload.get("id", "")).strip()
    description = str(payload.get("description", "")).strip()
    for field, value in (("id", experiment_id), ("description", description)):
        if not value:
            raise HTTPException(
                422, f"The experiment needs a {field}; it cannot be blank."
            )

    try:
        return build_experiment_document(
            experiment_id=experiment_id,
            description=description,
            personas=payload.get("personas", []),
            scenarios=payload.get("scenarios", []),
        )
    except CompilationError as exc:
        raise HTTPException(422, str(exc)) from exc


def _driver(interviewer: Interviewer) -> StepDriver:
    """The driver, with the matcher on the same gateway.

    Duplicated from the CLI's composition rather than shared with it: one adapter importing
    another is the boundary this package is arranged to prevent, and three lines is a cheaper
    price than a shared helper both doors would have to agree about.

    One gateway serves both chat and embeddings, so the interviewer *is* the embedder — when
    it can embed at all. A scripted provider cannot, and matching is the one part of a run
    that degrades to "no metric matched" instead of failing, so it is left off rather than
    faked.
    """
    from metis.wizard.application.driver import StepDriver
    from metis.wizard.application.matching import EmbeddingMatcher

    matcher = (
        EmbeddingMatcher(embedder=cast("Embedder", interviewer))
        if hasattr(interviewer, "embed")
        else None
    )
    return StepDriver(interviewer=interviewer, matcher=matcher)


def _view(session: Session) -> dict[str, Any]:
    """Everything the three panes need, in one payload.

    `next()` is called here rather than by the caller because composing the next screen is
    what makes the payload current — the conversation always ends at the screen you are
    looking at.
    """
    request = session.next()
    return {
        "id": session.state.id,
        "step": session.state.step.value,
        "busy_message": session.busy_message(),
        "done": request is None,
        "requests": [r.model_dump(mode="json") for r in session.state.requests],
        "profile": session.profile().model_dump(mode="json"),
    }


def create_app(
    *,
    interviewer_factory: Callable[..., Interviewer],
    root: Path = Path("evaluation"),
) -> FastAPI:
    """Compose the web door.

    The interviewer arrives as a factory for the same reason the CLI takes one: this module
    must not decide which model answers, so a test can drive the whole door with a scripted
    provider and never reach the network.
    """
    app = FastAPI(title="METIS wizard", docs_url=None, redoc_url=None)
    store = SessionStore(root)

    def _session(session_id: str) -> Session:
        path = store.path_for(session_id)
        if path is None:
            raise HTTPException(404, f"No session {session_id}.")
        try:
            return Session.resume(path, driver=_driver(_interviewer(session_id)))
        except SessionVersionError as exc:
            raise HTTPException(409, str(exc)) from exc

    def _interviewer(session_id: str | None = None) -> Interviewer:
        try:
            parameters = inspect.signature(interviewer_factory).parameters
        except (TypeError, ValueError):
            try:
                return interviewer_factory()
            except InterviewerUnavailable as exc:
                raise HTTPException(503, str(exc)) from exc

        try:
            session_parameter = parameters.get("session_id")
            accepts_keywords = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if accepts_keywords or session_parameter is not None:
                if (
                    session_parameter is not None
                    and session_parameter.kind is inspect.Parameter.POSITIONAL_ONLY
                ):
                    return interviewer_factory(session_id)
                return interviewer_factory(session_id=session_id)
            return interviewer_factory()
        except InterviewerUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc

    # ── sessions ───────────────────────────────────────────────────────────

    @app.get("/api/interview")
    def interview_configuration() -> dict[str, Any]:
        """Return package-owned copy needed before a session exists."""
        from metis.wizard.application.interview import load_interview_config

        config = load_interview_config()
        # Statuses are keyed by SessionStep; the door addresses them by the session's
        # current step string, so send the enum values as plain keys.
        return {
            "opening_question": config.opening_question,
            "statuses": {step.value: text for step, text in config.statuses.items()},
        }

    @app.get("/api/sessions")
    def list_sessions() -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "title": s.title,
                "step": s.step,
                "updated": s.updated,
            }
            for s in store.list()
        ]

    @app.post("/api/sessions")
    def create_session() -> dict[str, Any]:
        from metis.wizard.contracts import Product, ProductProfile

        session_id = f"wizard-{uuid.uuid4().hex[:8]}"
        profile = ProductProfile(product=Product(name="", description="", users=""))
        session = Session.start(
            profile,
            path=store.new_path(session_id),
            driver=_driver(_interviewer(session_id)),
            session_id=session_id,
        )
        return _view(session)

    @app.get("/api/sessions/{session_id}")
    def read_session(session_id: str) -> dict[str, Any]:
        return _view(_session(session_id))

    @app.post("/api/sessions/{session_id}/respond")
    def respond(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = _session(session_id)
        if session.state.pending is None:
            raise HTTPException(409, "Nothing to answer.")
        session.respond(_response_adapter.validate_python(payload))
        return _view(session)

    # ── output ─────────────────────────────────────────────────────────────

    @app.get("/api/sessions/{session_id}/experiment.yaml")
    def experiment(session_id: str) -> FileResponse:
        from metis.wizard.application.compile import write_experiment

        path = store.path_for(session_id)
        if path is None:
            raise HTTPException(404, f"No session {session_id}.")
        session = Session.resume(path)
        target = path.parent / "experiment.yaml"
        write_experiment(session.profile(), session.state.id, target)
        return FileResponse(target, filename="experiment.yaml")

    @app.get("/api/sessions/{session_id}/fixtures")
    def list_fixtures(session_id: str) -> list[dict[str, Any]]:
        path = store.path_for(session_id)
        if path is None:
            raise HTTPException(404, f"No session {session_id}.")
        return [item.model_dump(mode="json") for item in _fixture_library(path).list()]

    @app.post("/api/sessions/{session_id}/fixtures")
    def upload_fixtures(
        session_id: str,
        files: list[UploadFile] = File(default=[]),
    ) -> dict[str, Any]:
        path = store.path_for(session_id)
        if path is None:
            raise HTTPException(404, f"No session {session_id}.")
        library = _fixture_library(path)
        try:
            added = library.upload([(file.filename or "", file.file) for file in files])
        except FixtureError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "added": [item.model_dump(mode="json") for item in added],
            "fixtures": [item.model_dump(mode="json") for item in library.list()],
        }

    @app.delete("/api/sessions/{session_id}/fixtures/{filename}")
    def delete_fixture(session_id: str, filename: str) -> dict[str, Any]:
        path = store.path_for(session_id)
        if path is None:
            raise HTTPException(404, f"No session {session_id}.")
        session = Session.resume(path)
        try:
            _fixture_library(path).delete(
                filename,
                referenced=_profile_fixture_names(session),
            )
        except FixtureError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "fixtures": [
                item.model_dump(mode="json") for item in _fixture_library(path).list()
            ]
        }

    @app.get("/api/sessions/{session_id}/experiment.zip")
    def experiment_specification(session_id: str) -> FileResponse:
        path = store.path_for(session_id)
        if path is None:
            raise HTTPException(404, f"No session {session_id}.")
        session = Session.resume(path)
        temporary = temporary_specification_directory(
            prefix="metis-session-specification-"
        )
        try:
            profile = session.profile()
            document = compile_experiment(profile, session.state.id)
            target = temporary / "experiment.zip"
            write_specification(
                document,
                path.parent / "fixtures",
                target,
                profile=profile,
            )
        except (CompilationError, SpecificationError) as exc:
            _cleanup_directory(temporary)
            raise HTTPException(422, str(exc)) from exc
        except Exception:
            _cleanup_directory(temporary)
            raise
        return _specification_response(target, cleanup=temporary)

    # ── the hand-authoring door ──────────────────────────────────────────────
    #
    # The second way in: a form that authors the experiment document directly, with no
    # interview and no session. These two routes carry no state — the catalogue is read-only,
    # and the compile route holds the document only for the duration of its response. Neither
    # touches the store.

    @app.get("/api/metrics")
    def metrics() -> list[dict[str, Any]]:
        """The catalogue the form's metric picker offers.

        A single flat list, already sorted by the reader. The library re-exports every metric
        from one flat namespace, so there is no module segment to group on any more; the picker
        shows one alphabetical list rather than a section per module.
        """
        from metis.wizard.application.matching.library_catalogue import (
            library_catalogue,
        )

        return [
            {
                "fqn": spec.fqn,
                "name": spec.name,
                "description": spec.description,
            }
            for spec in library_catalogue()
        ]

    @app.post("/api/experiment.yaml")
    def compile_submitted(payload: dict[str, Any]) -> Response:
        """Compile a form submission into a downloadable document, storing nothing.

        The document arrives in schema shape; the compiler stamps the version, validates it,
        and serialises it through the same routine the interview's output uses. A submission
        the schema rejects returns a 422 with the offending location and no file — the browser
        gates on the same rules, so a rejection here is a safety net rather than the norm.
        """
        document = _submitted_document(payload)

        return Response(
            content=to_yaml(document),
            media_type="application/x-yaml",
            headers={"content-disposition": 'attachment; filename="experiment.yaml"'},
        )

    @app.post("/api/experiment.zip")
    def compile_submitted_specification(
        document: str = Form(...),
        files: list[UploadFile] = File(default=[]),
    ) -> FileResponse:
        try:
            payload = json.loads(document)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                422, "The experiment document must be valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(422, "The experiment document must be a JSON object.")

        compiled = _submitted_document(payload)
        temporary = temporary_specification_directory()
        try:
            library = FixtureLibrary(temporary / "fixtures")
            library.upload([(file.filename or "", file.file) for file in files])
            target = temporary / "experiment.zip"
            write_specification(compiled, library.root, target)
        except (FixtureError, SpecificationError) as exc:
            _cleanup_directory(temporary)
            raise HTTPException(422, str(exc)) from exc
        except Exception:
            _cleanup_directory(temporary)
            raise
        return _specification_response(target, cleanup=temporary)

    # ── the app itself ─────────────────────────────────────────────────────

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
