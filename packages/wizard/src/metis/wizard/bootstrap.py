"""Production composition root for the wizard.

This is the only module that assembles more than one adapter. Shared application code and the
CLI adapter depend on protocols; this module supplies the PlatformAI implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from metis.wizard.adapters.cli import commands
from metis.wizard.adapters.llm.gateway import GatewayInterviewer

if TYPE_CHECKING:
    from collections.abc import Callable

    import typer
    from fastapi import FastAPI

    from metis.wizard.application.interviewer import Interviewer


def platform_interviewer(session_id: str | None = None) -> Interviewer:
    """Construct the real gateway-backed interviewer for one CLI run."""
    return GatewayInterviewer(session_id=session_id)


def create_cli_app(
    interviewer_factory: Callable[..., Interviewer] = platform_interviewer,
) -> typer.Typer:
    """Compose the CLI with an interviewer provider.

    The optional factory is the test seam: the same Typer app and terminal loop can be driven
    with a deterministic provider without importing or calling the network gateway.
    """
    commands.configure(interviewer_factory=interviewer_factory)
    return commands.app


def create_web_app(
    interviewer_factory: Callable[..., Interviewer] = platform_interviewer,
    *,
    root: Path = Path("evaluation"),
) -> FastAPI:
    """Compose the web door.

    FastAPI is imported here rather than at module scope because the web door is an optional
    extra: a CLI-only install has no framework, and importing this module to get `cli_app`
    must not require one.
    """
    from metis.wizard.adapters.web.server import create_app

    return create_app(interviewer_factory=interviewer_factory, root=root)


cli_app = create_cli_app()


@cli_app.command()
def serve(
    root: Path = Path("evaluation"),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Open the wizard in a browser.

    Registered here rather than in the CLI adapter's `commands` module: this starts the web
    door, so it is composition, and composition is what this module is for. It also keeps the
    CLI adapter free of any knowledge that another door exists.
    """
    import typer
    import uvicorn

    commands._load_env()
    typer.echo(f"Wizard at http://{host}:{port} — sessions in {root}/")
    uvicorn.run(create_web_app(root=root), host=host, port=port, log_level="warning")


__all__ = [
    "cli_app",
    "create_cli_app",
    "create_web_app",
    "platform_interviewer",
    "serve",
]
