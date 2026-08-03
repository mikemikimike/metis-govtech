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

from fastapi import FastAPI, HTTPException
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

    # ── the app itself ─────────────────────────────────────────────────────

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
