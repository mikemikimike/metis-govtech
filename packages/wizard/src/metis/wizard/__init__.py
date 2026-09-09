"""metis.wizard — Evaluation config generator.

The names exported here are the headless package facade. Doors and providers live behind
internal modules so moving them does not change the imports used by callers.
"""

from importlib.metadata import PackageNotFoundError, version

from metis.core import Status
from metis.core import __version__ as core_version
from metis.wizard.application import (
    InterviewState,
    compile_profile,
    derive_stage,
    handle_interview,
    package_specification,
)
from metis.wizard.application.compile import (
    CompilationError,
    SpecificationError,
    SpecificationFixture,
    compile_experiment,
    render_review,
    write_experiment,
    write_review,
)
from metis.wizard.application.config import working_status
from metis.wizard.application.interviewer import InterviewerUnavailable
from metis.wizard.application.matching.library_catalogue import (
    library_catalogue as _library_catalogue,
)
from metis.wizard.contracts import (
    AnyRequest,
    AnyResponse,
    ChatRequest,
    ChatResponse,
    ChoiceRequest,
    ChoiceResponse,
    CompileResult,
    FormRequest,
    FormResponse,
    InterviewEndRequest,
    InterviewErrorCode,
    InterviewFailure,
    InterviewOutcome,
    InterviewRequest,
    InterviewResult,
    InterviewStartRequest,
    InterviewSuccess,
    InterviewTurnRequest,
    MissingData,
    MissingDataCode,
    ProductProfile,
    UserResponse,
    WizardRequest,
)
from metis.wizard.contracts.metric_spec import MetricSummary
from metis.wizard.domain.permissions import InterviewStep


def configure_interview_runtime(*, api_key: str, base_url: str, model: str) -> None:
    """Configure the production collaborators used by :func:`handle_interview`."""
    from metis.wizard.bootstrap import configure_interview_runtime

    configure_interview_runtime(api_key=api_key, base_url=base_url, model=model)


def metric_catalogue() -> list[MetricSummary]:
    """Return installed metric display metadata without exposing matcher internals."""
    return [
        MetricSummary(
            fqn=spec.fqn,
            name=spec.name,
            description=spec.description,
        )
        for spec in _library_catalogue()
    ]


try:
    __version__ = version("metis-wizard")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "AnyRequest",
    "AnyResponse",
    "ChatRequest",
    "ChatResponse",
    "CompilationError",
    "CompileResult",
    "ChoiceRequest",
    "ChoiceResponse",
    "FormRequest",
    "FormResponse",
    "InterviewEndRequest",
    "InterviewErrorCode",
    "InterviewFailure",
    "InterviewOutcome",
    "InterviewRequest",
    "InterviewResult",
    "InterviewStartRequest",
    "InterviewState",
    "InterviewSuccess",
    "InterviewTurnRequest",
    "InterviewStep",
    "InterviewerUnavailable",
    "MissingData",
    "MissingDataCode",
    "MetricSummary",
    "ProductProfile",
    "SpecificationFixture",
    "SpecificationError",
    "Status",
    "UserResponse",
    "WizardRequest",
    "__version__",
    "compile_experiment",
    "compile_profile",
    "configure_interview_runtime",
    "core_version",
    "derive_stage",
    "handle_interview",
    "metric_catalogue",
    "package_specification",
    "render_review",
    "write_experiment",
    "write_review",
    "working_status",
]
