"""The wizard Interview lifecycle routes and Profile compilation route.

The router does no wizard work. It receives a typed body, calls the public wizard facade, and maps
the typed result onto an HTTP status. No stage, Profile, prompt, matching or compilation rule lives
here — those all stay inside metis-wizard.

Status mapping (from the design):

| result                                          | status |
|-------------------------------------------------|-------:|
| successful start, turn, end, or compile        |    200 |
| valid JSON with invalid state or stale id       |    400 |
| exhausted model retries, unchanged state        |    503 |
| unexpected non-retryable failure                |    500 |

Request/Profile schema failures become 422 through the app's validation handler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from metis.wizard import (
    CompilationError,
    CompileResult,
    InterviewEndRequest,
    InterviewErrorCode,
    InterviewFailure,
    InterviewResult,
    InterviewStartRequest,
    InterviewTurnRequest,
    ProductProfile,
    compile_profile,
)

if TYPE_CHECKING:
    from metis.api.settings import WizardDependencies

router = APIRouter(prefix="/api/v1/wizard", tags=["wizard"])

# Only two failure codes are not a plain caller error: an exhausted model gateway is a transient
# service condition, and an unexpected fault is a bug. Every other code is the client's to fix.
_STATUS: dict[InterviewErrorCode, int] = {
    InterviewErrorCode.MODEL_UNAVAILABLE: 503,
    InterviewErrorCode.INTERNAL_ERROR: 500,
}


class ServiceError(BaseModel):
    """The stable error body for compile and validation failures.

    It shares its shape — `type`, `code`, `message`, `retryable` — with `InterviewFailure`, so a
    client parses every failure the same way whichever route raised it.
    """

    type: Literal["failure"] = "failure"
    code: str
    message: str
    retryable: bool = False


def get_dependencies(request: Request) -> WizardDependencies:
    """Return the startup-composed public Interview handler."""
    dependencies = getattr(request.app.state, "wizard_dependencies", None)
    if dependencies is None:
        raise RuntimeError(
            "Wizard dependencies were not composed at application startup."
        )
    return dependencies


@router.post(
    "/interview/start",
    summary="Start a wizard Interview from its product description",
    response_model=InterviewResult,
    responses={
        400: {"model": InterviewFailure},
        422: {"model": ServiceError},
        500: {"model": InterviewFailure},
        503: {"model": InterviewFailure},
    },
)
def start(
    body: InterviewStartRequest,
    dependencies: WizardDependencies = Depends(get_dependencies),
) -> JSONResponse:
    """Create client-held Interview state from the user's initial raw description."""
    result = dependencies.interview_handler(body)
    return _result_response(result)


@router.post(
    "/interview/turn",
    summary="Answer the pending request in one wizard Interview",
    response_model=InterviewResult,
    responses={
        400: {"model": InterviewFailure},
        422: {"model": ServiceError},
        500: {"model": InterviewFailure},
        503: {"model": InterviewFailure},
    },
)
def turn(
    body: InterviewTurnRequest,
    dependencies: WizardDependencies = Depends(get_dependencies),
) -> JSONResponse:
    """Apply one typed response to the client's complete current Interview state."""
    result = dependencies.interview_handler(body)
    return _result_response(result)


@router.post(
    "/interview/end",
    summary="Best-effort finish one wizard Interview",
    response_model=InterviewResult,
    responses={
        400: {"model": InterviewFailure},
        422: {"model": ServiceError},
        500: {"model": InterviewFailure},
        503: {"model": InterviewFailure},
    },
)
def end(
    body: InterviewEndRequest,
    dependencies: WizardDependencies = Depends(get_dependencies),
) -> JSONResponse:
    """Run best-effort completion on the client's complete current Interview state."""
    result = dependencies.interview_handler(body)
    return _result_response(result)


def _result_response(result: InterviewResult) -> JSONResponse:
    """Map one public Interview result to its stable HTTP status and JSON body."""
    if isinstance(result, InterviewFailure):
        status = _STATUS.get(result.code, 400)
        return JSONResponse(result.model_dump(mode="json"), status_code=status)
    return JSONResponse(result.model_dump(mode="json"), status_code=200)


@router.post(
    "/compile",
    summary="Compile a finished wizard Profile into YAML",
    response_model=CompileResult,
    responses={
        400: {"model": ServiceError},
        422: {"model": ServiceError},
        500: {"model": ServiceError},
    },
)
def compile_(profile: ProductProfile) -> JSONResponse:
    """Convert a runnable `ProductProfile` into the two final configuration documents.

    The response contains `profile.yaml` and `experiment.yaml` as strings. The API returns the
    content only; it does not write files or save the Profile on the server.
    """
    try:
        result = compile_profile(profile)
    except CompilationError as exc:
        error = ServiceError(
            code="compilation_failed", message=str(exc), retryable=False
        )
        return JSONResponse(error.model_dump(), status_code=400)
    return JSONResponse(result.model_dump(mode="json", by_alias=True), status_code=200)


__all__ = ["ServiceError", "router"]
