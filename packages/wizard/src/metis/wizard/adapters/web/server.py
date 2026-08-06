"""The web door.

The same two lines every door runs, taken one turn at a time. A browser cannot hold a
conversation in a process variable between requests, so each one loads the session, applies at
most one response, and saves — which is the arrangement `SessionState` was split out for.

Nothing here composes a sentence about the domain. The payload carries the requests the
package composed and the profile it built; the words are all already in them.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter

from metis.wizard.adapters.web.store import SessionStore
from metis.wizard.application import Session, SessionVersionError
from metis.wizard.application.interviewer import Interviewer, InterviewerUnavailable
from metis.wizard.contracts.conversation import AnyResponse

_response_adapter: TypeAdapter[AnyResponse] = TypeAdapter(AnyResponse)

STATIC_DIR = Path(__file__).parent / "static"


def _driver(interviewer: Interviewer):
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
    from metis.wizard.application.matching.matcher import Embedder

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
    interviewer_factory: Callable[[], Interviewer],
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
            return Session.resume(path, driver=_driver(_interviewer()))
        except SessionVersionError as exc:
            raise HTTPException(409, str(exc)) from exc

    def _interviewer() -> Interviewer:
        try:
            return interviewer_factory()
        except InterviewerUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc

    # ── sessions ───────────────────────────────────────────────────────────

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
        profile = ProductProfile(product=Product(name="", summary="", users=""))
        session = Session.start(
            profile,
            path=store.new_path(session_id),
            driver=_driver(_interviewer()),
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
        from metis.wizard.application.compile import (
            CompilationError,
            build_experiment_document,
            to_yaml,
        )

        # The schema requires id and description be present, but not that they carry text — an
        # experiment with a blank id or description is one no reader can act on, so the form
        # gates on both and this route holds the same line as its safety net. The interview's
        # own compiler is left untouched: this presence rule is the hand-authoring door's, not
        # a change to what the schema means.
        experiment_id = str(payload.get("id", "")).strip()
        description = str(payload.get("description", "")).strip()
        for field, value in (("id", experiment_id), ("description", description)):
            if not value:
                raise HTTPException(
                    422, f"The experiment needs a {field}; it cannot be blank."
                )

        try:
            document = build_experiment_document(
                experiment_id=experiment_id,
                description=description,
                personas=payload.get("personas", []),
                scenarios=payload.get("scenarios", []),
            )
        except CompilationError as exc:
            raise HTTPException(422, str(exc)) from exc

        return Response(
            content=to_yaml(document),
            media_type="application/x-yaml",
            headers={"content-disposition": 'attachment; filename="experiment.yaml"'},
        )

    # ── the app itself ─────────────────────────────────────────────────────

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
