"""The wizard's commands.

Thin on purpose. `init` and `resume` both build a session and hand it to the door; the loop
they run is the same two lines any door runs.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable
from pathlib import Path

import typer

from metis.wizard import __version__, core_version
from metis.wizard.application.interviewer import Interviewer, InterviewerUnavailable
from metis.wizard.application.runs import format_runs

app = typer.Typer(help="Generate METIS evaluation configurations.")
_interviewer_factory: Callable[..., Interviewer] | None = None


def configure(*, interviewer_factory: Callable[..., Interviewer]) -> None:
    """Inject the provider used by commands.

    The CLI adapter deliberately does not import a concrete gateway. The composition root
    supplies one for production, while tests can supply a scripted interviewer here.
    """
    global _interviewer_factory
    _interviewer_factory = interviewer_factory


def _new_interviewer(session_id: str | None = None) -> Interviewer:
    if _interviewer_factory is None:
        raise RuntimeError(
            "The wizard CLI is not composed. Use metis.wizard.bootstrap.cli_app."
        )
    factory = _interviewer_factory
    try:
        parameters = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return factory()

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
            return factory(session_id)
        return factory(session_id=session_id)
    return factory()


def _bind_session_id(interviewer: Interviewer, session_id: str) -> None:
    """Attach a loaded session id to the concrete gateway before its first model call."""
    if hasattr(interviewer, "session_id"):
        object.__setattr__(interviewer, "session_id", session_id)


def version_callback(value: bool):
    if value:
        typer.echo(f"metis-wizard {__version__} (core {core_version})")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True
    ),
):
    """Turn a description of your product into a runnable evaluation."""


def _run(session, out_dir: Path) -> None:
    """The corridor. Two lines, then write what it produced."""
    from rich.console import Console

    from metis.wizard.adapters.cli.render import render
    from metis.wizard.application.compile import write_experiment, write_review

    console = Console()

    # The header is drawn only when the step changes. Consecutive screens of one step (the
    # clarify questions, a mid-step form) already carry the same title and position, so
    # repeating the panel above each is noise. `step` is the finished value the package
    # stamped; the door compares it, it does not compute it.
    last_step = None
    while (request := _next_with_status(session, console)) is not None:
        response = render(request, show_header=request.step != last_step)
        _respond_with_status(session, response, console)
        last_step = request.step

    out_dir.mkdir(parents=True, exist_ok=True)
    experiment = out_dir / "experiment.yaml"
    review = out_dir / "review.md"
    profile = out_dir / "profile.yaml"
    write_experiment(session.profile(), session.state.id, experiment)
    write_review(session.profile(), session.state.id, review)
    # The profile is the spec the engine's verdict report joins results onto; it rides
    # beside the experiment so `simulate` freezes it into the run's inputs/.
    session.profile().save(profile)

    typer.echo(f"\nWrote {experiment}")
    typer.echo(f"Wrote {review}")
    typer.echo(f"Wrote {profile}")
    typer.echo(f"\n{format_runs(session.profile().run_count())} when you run this.")


def _next_with_status(session, console):
    """Compose the next screen behind a spinner.

    Some model calls happen inside `session.next()`, before a request exists — so without this
    the terminal simply stops for several seconds with nothing on screen. The application
    facade supplies the wording; the door only chooses the terminal presentation.

    `console.status` disables its live animation when the console is not a terminal, so a
    redirected or piped run degrades to silence rather than leaking control sequences into
    the transcript. Cheap composes (a chip toggle) flash it too briefly to notice; only the
    model calls linger, which is exactly when it earns its place.
    """
    with console.status(session.busy_message(), spinner="dots"):
        return session.next()


def _respond_with_status(session, response, console) -> None:
    """Apply a response behind the same package-authored status as the web door.

    Criteria generation and model-assisted edits happen during `respond()`, not `next()`.
    Wrapping both halves of the corridor keeps every slow path acknowledged.
    """
    with console.status(session.busy_message(), spinner="dots"):
        session.respond(response)


def _load_env() -> list[Path]:
    """Read `.env` files, searching only inside the project.

    `load_dotenv()` with no arguments walks *up* from the working directory until it finds a
    file — which, run from this repo, walks past the repo entirely and loads `~/.env`. Reading
    a credentials file from outside the project because nothing inside matched is not a
    default worth having, so the search is an explicit list instead.

    Existing environment variables win: a `.env` fills gaps, it does not override a variable
    you exported deliberately.

    Returns the files actually loaded, so a command can say where its credentials came from.
    """
    from dotenv import load_dotenv

    package_root = Path(__file__).resolve().parents[3]  # .../packages/wizard
    repo_root = package_root.parents[1]

    loaded = []
    for candidate in (Path.cwd() / ".env", package_root / ".env", repo_root / ".env"):
        if candidate.is_file() and candidate not in loaded:
            load_dotenv(candidate, override=False)
            loaded.append(candidate)
    return loaded


def _session_path(out_dir: Path) -> Path:
    return out_dir / "session.json"


def _driver(interviewer):
    """The driver, with the matcher wired to the same gateway.

    The matcher is not optional in a real run. Without it every criterion keeps
    `metric_fqn=None`, the compiler drops it from the scenario's metric list, and the experiment
    comes out with empty `metric_refs` — it validates, it loads, and it measures nothing at
    all. `test_cli.py` guards this.

    One gateway serves both chat and embeddings, so the interviewer *is* the embedder.
    """
    from metis.wizard.application.driver import StepDriver
    from metis.wizard.application.matching import EmbeddingMatcher

    return StepDriver(
        interviewer=interviewer, matcher=EmbeddingMatcher(embedder=interviewer)
    )


@app.command()
def init(
    out_dir: Path = typer.Option(
        Path("evaluation"),
        "--out-dir",
        help="Where to write the experiment and review.",
    ),
    restart: bool = typer.Option(
        False,
        "--restart",
        help="Discard an interview already in progress and start over.",
    ),
) -> None:
    """Start a new interview."""
    from metis.wizard.application import Session
    from metis.wizard.contracts import Product, ProductProfile

    # Refuse before anything else — the filesystem check costs no model call and needs no
    # credentials, so an accidental re-run of `init` reports the collision rather than
    # overwriting twenty minutes of interview on the first save(). `--restart` is the one
    # way past this, and it has to be typed.
    session_path = _session_path(out_dir)
    if session_path.is_file() and not restart:
        typer.echo(
            f"Error: an interview is already in progress at {session_path}.\n\n"
            f"  metis wizard resume            continue it\n"
            f"  metis wizard init --restart    discard it and start over",
            err=True,
        )
        raise typer.Exit(1)

    for env_file in _load_env():
        typer.echo(f"Read credentials from {env_file}")

    try:
        # Checked before anything else happens, so a missing key costs nothing and is
        # reported as the environment problem it is.
        session_id = f"wizard-{uuid.uuid4().hex[:8]}"
        interviewer = _new_interviewer(session_id)
    except InterviewerUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    # The opening question collects the name. Keep it empty so the model writes what the user
    # actually established instead of preserving a door-owned placeholder in the document.
    profile = ProductProfile(product=Product(name="", summary="", users=""))
    session = Session.start(
        profile,
        path=_session_path(out_dir),
        driver=_driver(interviewer),
        session_id=session_id,
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    _run(session, out_dir)


@app.command()
def resume(
    out_dir: Path = typer.Option(
        Path("evaluation"), "--out-dir", help="The directory holding session.json."
    ),
) -> None:
    """Pick up an interview where it left off."""
    from metis.wizard.application import Session, SessionVersionError

    path = _session_path(out_dir)
    if not path.is_file():
        typer.echo(f"Error: no session to resume at {path}.", err=True)
        raise typer.Exit(1)

    _load_env()

    try:
        interviewer = _new_interviewer()
    except InterviewerUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        session = Session.resume(path, driver=_driver(interviewer))
    except SessionVersionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    _bind_session_id(interviewer, session.state.id)

    typer.echo(f"Resuming at the {session.state.step} step.")
    _run(session, out_dir)
