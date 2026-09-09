"""The wizard Interview lifecycle, compilation, and package routes.

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

import json
from contextlib import suppress
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError

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
    SpecificationError,
    SpecificationFixture,
    compile_profile,
    package_specification,
    working_status,
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


class InterviewConfig(BaseModel):
    """Package-owned presentation text needed by an Interview client."""

    working_status: str


def get_dependencies(request: Request) -> WizardDependencies:
    """Return the startup-composed public Interview handler."""
    dependencies = getattr(request.app.state, "wizard_dependencies", None)
    if dependencies is None:
        raise RuntimeError(
            "Wizard dependencies were not composed at application startup."
        )
    return dependencies


@router.get(
    "/config",
    summary="Get package-owned wizard client configuration",
    response_model=InterviewConfig,
    responses={500: {"model": ServiceError}},
)
def config() -> InterviewConfig:
    """Return presentation text without copying it into the HTTP client."""
    return InterviewConfig(working_status=working_status())


@router.post(
    "/package",
    summary="Package a wizard Profile and fixtures into a ZIP",
    response_class=Response,
    response_model=None,
    responses={
        200: {
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}}
            }
        },
        400: {"model": ServiceError},
        422: {"model": ServiceError},
        500: {"model": ServiceError},
    },
)
def package(
    profile: str = Form(...),
    files: list[UploadFile] | None = File(default=None),
) -> Response | JSONResponse:
    """Build one request-scoped engine-ready ZIP without retaining uploaded files."""
    uploads = files or []
    try:
        parsed = ProductProfile.model_validate_json(profile)
        fixtures: list[SpecificationFixture] = []
        for upload in uploads:
            fixtures.append(
                SpecificationFixture(
                    name=upload.filename or "",
                    stream=upload.file,
                )
            )
        archive = package_specification(parsed, fixtures)
    except (json.JSONDecodeError, ValidationError):
        return JSONResponse(
            ServiceError(
                code="validation_error",
                message="The submitted Profile is invalid.",
                retryable=False,
            ).model_dump(),
            status_code=400,
        )
    except (CompilationError, SpecificationError) as exc:
        return JSONResponse(
            ServiceError(
                code="compilation_failed",
                message=str(exc),
                retryable=False,
            ).model_dump(),
            status_code=400,
        )
    finally:
        for upload in uploads:
            with suppress(OSError):
                upload.file.close()
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="experiment.zip"'},
    )


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


__all__ = ["InterviewConfig", "ServiceError", "router"]
