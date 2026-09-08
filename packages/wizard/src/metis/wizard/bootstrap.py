"""Production composition root for the wizard.

This is the only module that assembles more than one adapter. Shared application code and the
CLI adapter depend on protocols; this module supplies the PlatformAI implementation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from metis.wizard.adapters.cli import commands
from metis.wizard.adapters.llm.gateway import GatewayInterviewer

if TYPE_CHECKING:
    from collections.abc import Callable

    import typer

    from metis.wizard.application.interviewer import Interviewer


def platform_interviewer(interview_id: str | None = None) -> Interviewer:
    """Construct the real gateway-backed interviewer for one CLI run."""
    return GatewayInterviewer(interview_id=interview_id)


def configure_interview_runtime(*, api_key: str, base_url: str, model: str) -> None:
    """Install the production Interviewer and matcher used by the public Interview function.

    Provider construction stays in this composition root. Callers provide connection settings and
    never need to import or operate the gateway, matcher, or driver objects.
    """
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["INTERVIEW_MODEL"] = model

    from metis.wizard.application.matching import EmbeddingMatcher
    from metis.wizard.application.turn import configure_interview_dependencies

    interviewer = GatewayInterviewer()
    configure_interview_dependencies(
        interviewer, EmbeddingMatcher(embedder=interviewer)
    )


def create_cli_app(
    interviewer_factory: Callable[..., Interviewer] = platform_interviewer,
) -> typer.Typer:
    """Compose the CLI with an interviewer provider.

    The optional factory is the test seam: the same Typer app and terminal loop can be driven
    with a deterministic provider without importing or calling the network gateway.
    """
    commands.configure(interviewer_factory=interviewer_factory)
    return commands.app


cli_app = create_cli_app()


__all__ = [
    "cli_app",
    "configure_interview_runtime",
    "create_cli_app",
    "platform_interviewer",
]
