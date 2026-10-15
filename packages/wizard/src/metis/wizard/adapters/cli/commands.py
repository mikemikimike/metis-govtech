"""The wizard's commands.

Thin on purpose. The interview state is client-held, so the CLI keeps it in a JSON file and is
just another door over `handle_interview`: send a concrete lifecycle request, render the pending
screen, and send the answer back. `init` starts from the user's description and ARC capability
evidence; `resume` reloads the saved state and answers its pending screen. The corridor both run
is the same loop.
"""

from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import typer

from metis.core.console import console
from metis.wizard import (
    InterviewerUnavailable,
    InterviewFailure,
    InterviewRequest,
    InterviewStartRequest,
    InterviewState,
    InterviewStep,
    InterviewTurnRequest,
    __version__,
    compile_specification,
    core_version,
    derive_stage,
    handle_interview,
)
from metis.wizard.application import export_layout
from metis.wizard.application.trials import format_trials

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

    from metis.wizard.application.interviewer import Interviewer


app = typer.Typer(help="Generate METIS evaluation configurations.")
_interviewer_factory: Callable[..., Interviewer] | None = None


def configure(*, interviewer_factory: Callable[..., Interviewer]) -> None:
    """Inject the provider used by commands.

    The CLI adapter deliberately does not import a concrete gateway. The composition root
    supplies one for production, while tests can supply a scripted interviewer here.
    """
    global _interviewer_factory
    _interviewer_factory = interviewer_factory


def _new_interviewer(interview_id: str | None = None) -> Interviewer:
    if _interviewer_factory is None:
        raise RuntimeError(
            "The wizard CLI is not composed. Use metis.wizard.bootstrap.cli_app."
        )
    factory = _interviewer_factory
    try:
        parameters = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return factory()

    id_parameter = parameters.get("interview_id")
    accepts_keywords = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_keywords or id_parameter is not None:
        if (
            id_parameter is not None
            and id_parameter.kind is inspect.Parameter.POSITIONAL_ONLY
        ):
            return factory(interview_id)
        return factory(interview_id=interview_id)
    return factory()


def _matcher(interviewer: Interviewer) -> object:
    """The grader matcher, wired to the same gateway.

    Every Criterion needs a Grader before the specification can be exported.

    One gateway serves both chat and embeddings, so the interviewer *is* the embedder.
    """
    from metis.wizard.application.matching import EmbeddingMatcher

    return EmbeddingMatcher(embedder=interviewer)  # type: ignore[arg-type]


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"metis-wizard {__version__} (core {core_version})")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True
    ),
) -> None:
    """Turn a description of your target into a runnable evaluation."""


# ── the corridor ─────────────────────────────────────────────────────────────


def _busy_message(state: InterviewState | None) -> str:
    """The package-owned status for the stage an operation is about to work on."""
    from metis.wizard.application import config

    if state is None:
        return config.status_for(InterviewStep.CLARIFY)
    if state.pending is not None and state.pending.stage is not None:
        return config.status_for(state.pending.stage)
    return config.status_for(derive_stage(state))


def _drive(
    request: InterviewRequest,
    *,
    interviewer: Interviewer,
    matcher: object,
    out_dir: Path,
    console: Console,
) -> InterviewState:
    """Run Interview operations until DONE, persisting returned state after each success.

    A model call happens inside `handle_interview`, before any screen exists — so the spinner wraps
    the whole operation, using the package-authored status for the stage. The header is redrawn only
    when the step position changes, so a run of clarify questions does not repeat the panel.
    """
    from metis.wizard.adapters.cli.render import render

    last_step: int | None = None
    while True:
        state = None if isinstance(request, InterviewStartRequest) else request.state
        with console.status(_busy_message(state), spinner="dots"):
            result = handle_interview(
                request,
                interviewer=interviewer,
                matcher=matcher,
            )
        if isinstance(result, InterviewFailure):
            # A retryable failure — usually the model was unreachable — leaves the state
            # unchanged, so resending the same request is safe. The door acts on the flag the
            # contract exposes; a non-retryable failure always stops here.
            if result.retryable and _retry_confirmed(result):
                continue
            _fail(result)

        state = result.state
        _save(state, out_dir)
        if result.outcome == "done":
            return state

        pending = state.pending
        if pending is None:
            raise RuntimeError(
                "An awaiting Interview result must include a pending request."
            )
        response = render(pending, show_header=pending.step != last_step)
        last_step = pending.step
        request = InterviewTurnRequest(
            state=state, request_id=pending.request_id or "", response=response
        )


def _retry_confirmed(failure: InterviewFailure) -> bool:
    """After a retryable failure, ask whether to run the same operation again.

    The failure changed nothing, so the same request is safe to resend. Only a terminal can
    answer, so a non-interactive run does not retry and falls through to the normal error report.
    """
    if not sys.stdin.isatty():
        return False
    return typer.confirm(f"{failure.message} Try again?", default=True)


def _fail(failure: InterviewFailure) -> NoReturn:
    """Report an Interview failure and stop. Any structured gaps are listed under the message."""
    typer.echo(f"Error: {failure.message}", err=True)
    for gap in failure.missing:
        typer.echo(f"  - {gap.message}", err=True)
    raise typer.Exit(1)


def _write_outputs(state: InterviewState, out_dir: Path) -> None:
    """Save the final state and review, then publish the completed Specification."""
    from metis.wizard.application.compile import render_review
    from metis.wizard.application.turn import experiment_id

    specification = state.specification
    compiled = compile_specification(specification)
    review = render_review(specification, experiment_id(specification))

    _save(state, out_dir)
    (out_dir / export_layout.FIXTURES).mkdir(parents=True, exist_ok=True)
    specification_path = out_dir / export_layout.SPECIFICATION
    review_path = out_dir / export_layout.REVIEW
    review_path.write_text(review, encoding="utf-8")
    # Publish the completion marker only after every other file is saved.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=specification_path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            temporary.write(compiled.specification_yaml)
            temporary.close()
            temporary_path.replace(specification_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    typer.echo(f"\nWrote {specification_path}")
    typer.echo(f"Wrote {review_path}")
    typer.echo(f"\n{format_trials(specification.trial_count())} when you run this.")


# ── state persistence (client-held) ────────────────────────────────────────────


def _state_path(out_dir: Path) -> Path:
    return out_dir / export_layout.INTERVIEW_STATE


def _save(state: InterviewState, out_dir: Path) -> None:
    """Persist the client-held state so an interrupted interview can resume from it."""
    _state_path(out_dir).parent.mkdir(parents=True, exist_ok=True)
    (out_dir / export_layout.SPECIFICATION).unlink(missing_ok=True)
    _state_path(out_dir).write_text(state.model_dump_json(), encoding="utf-8")


def _load(out_dir: Path) -> InterviewState:
    return InterviewState.model_validate_json(
        _state_path(out_dir).read_text(encoding="utf-8")
    )


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


# ── commands ───────────────────────────────────────────────────────────────


@app.command()
def init(
    description: str = typer.Argument(
        ..., help="A raw description of the target or agent to evaluate."
    ),
    out_dir: Path = typer.Option(
        Path("evaluation"),
        "--out-dir",
        help="The experiment root for inputs/ and outputs/.",
    ),
    restart: bool = typer.Option(
        False,
        "--restart",
        help="Discard an interview already in progress and start over.",
    ),
) -> None:
    """Start a new interview."""
    # Refuse before anything else — the filesystem check costs no model call and needs no
    # credentials, so an accidental re-run of `init` reports the collision rather than
    # overwriting an interview in progress. `--restart` is the one way past this.
    state_path = _state_path(out_dir)
    if (out_dir / export_layout.SPECIFICATION).is_file() and not restart:
        typer.echo(
            "Error: this export is complete. Use --restart to start a new Interview.",
            err=True,
        )
        raise typer.Exit(1)
    if state_path.is_file() and not restart:
        typer.echo(
            f"Error: an interview is already in progress at {state_path}.\n\n"
            f"  metis wizard resume            continue it\n"
            f"  metis wizard init <description> --restart    discard it and start over",
            err=True,
        )
        raise typer.Exit(1)

    for env_file in _load_env():
        typer.echo(f"Read credentials from {env_file}")

    try:
        # Checked before anything else happens, so a missing key costs nothing and is
        # reported as the environment problem it is.
        interviewer = _new_interviewer()
    except InterviewerUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    from metis.wizard.adapters.cli.opening import read_capability_evidence

    known_capability_ids, capability_confidence = read_capability_evidence(
        out=console.print
    )
    state = _drive(
        InterviewStartRequest(
            description=description,
            known_capability_ids=known_capability_ids,
            capability_confidence=capability_confidence,
        ),
        interviewer=interviewer,
        matcher=_matcher(interviewer),
        out_dir=out_dir,
        console=console,
    )
    _write_outputs(state, out_dir)


@app.command()
def resume(
    out_dir: Path = typer.Option(
        Path("evaluation"),
        "--out-dir",
        help="The experiment root holding inputs/interview_state.json.",
    ),
) -> None:
    """Pick up an interview where it left off."""
    from metis.wizard.adapters.cli.render import render

    if (out_dir / export_layout.SPECIFICATION).is_file():
        typer.echo("This export is complete.")
        return
    path = _state_path(out_dir)
    if not path.is_file():
        typer.echo(f"Error: no interview to resume at {path}.", err=True)
        raise typer.Exit(1)

    state = _load(out_dir)
    if state.pending is None:
        _write_outputs(state, out_dir)
        return

    _load_env()

    try:
        interviewer = _new_interviewer()
    except InterviewerUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Resuming at the {state.pending.stage} step.")

    # The saved state already holds the screen the interview stopped on; answer that first, then
    # hand the resulting Interview request to the same corridor `init` runs.
    request = state.pending
    response = render(request, show_header=True)
    interview_request = InterviewTurnRequest(
        state=state,
        request_id=request.request_id or "",
        response=response,
    )

    state = _drive(
        interview_request,
        interviewer=interviewer,
        matcher=_matcher(interviewer),
        out_dir=out_dir,
        console=console,
    )
    _write_outputs(state, out_dir)
