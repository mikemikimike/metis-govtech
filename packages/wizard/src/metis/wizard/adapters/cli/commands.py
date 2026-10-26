"""The wizard's commands.

Thin on purpose. The interview state is client-held, so the CLI keeps it in a JSON file and is
just another door over `handle_interview`: send a concrete lifecycle request, render the pending
screen, and send the answer back. `init` starts from the user's description and ARC capability
evidence; `resume` reloads the saved state and answers its pending screen. The corridor both run
is the same loop.
"""

from __future__ import annotations

import inspect
import shlex
import sys
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import typer
import yaml

from metis.core.console import console
from metis.wizard import (
    InterviewerUnavailable,
    InterviewFailure,
    InterviewRequest,
    InterviewStartRequest,
    InterviewState,
    InterviewStep,
    InterviewTurnRequest,
    TargetConnection,
    __version__,
    compile_specification,
    core_version,
    derive_stage,
    handle_interview,
    set_connection,
)
from metis.wizard.application import export_layout
from metis.wizard.application.trials import format_trials

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

    from metis.wizard import Specification
    from metis.wizard.application.interviewer import Interviewer


app = typer.Typer(help="Generate METIS evaluation configurations.")


class Mode(StrEnum):
    """`spec` writes a Specification only. `run` also connects the target."""

    SPEC = "spec"
    RUN = "run"


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


def _warn_without_embeddings() -> None:
    """Say once that grader matching is off when the embeddings role has no key."""
    import os

    from metis.wizard.application.matching import embeddings_warning

    warning = embeddings_warning(os.environ)
    if warning is not None:
        typer.echo(f"Warning: {warning}", err=True)


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


def _confirm(prompt: str) -> bool:
    return typer.confirm(prompt, default=False)


def _fail(failure: InterviewFailure) -> NoReturn:
    """Report an Interview failure and stop. Any structured gaps are listed under the message."""
    typer.echo(f"Error: {failure.message}", err=True)
    for gap in failure.missing:
        typer.echo(f"  - {gap.message}", err=True)
    raise typer.Exit(1)


def _write_outputs(
    state: InterviewState, out_dir: Path, *, connection_skipped: bool = False
) -> None:
    """Save the final state, review, and binding, then publish the completed Specification."""
    from metis.wizard.application.compile import render_review
    from metis.wizard.application.connection import (
        binding_yaml,
        connected_specification,
    )
    from metis.wizard.application.turn import experiment_id

    connection = state.context.connection
    specification = connected_specification(state.specification, connection)
    compiled = compile_specification(specification)
    review = render_review(
        specification,
        experiment_id(specification),
        connection=connection,
        connection_skipped=connection_skipped,
    )

    _save(state, out_dir)
    from metis.wizard.adapters.cli.documents import publish_task_fixtures

    missing_fixtures = publish_task_fixtures(
        [task.fixtures for task in specification.tasks],
        out_dir / export_layout.DOCUMENTS,
        out_dir / export_layout.FIXTURES,
    )
    specification_path = out_dir / export_layout.SPECIFICATION
    review_path = out_dir / export_layout.REVIEW
    review_path.write_text(review, encoding="utf-8")
    binding_path = out_dir / export_layout.TARGET_BINDING
    if connection is not None:
        binding_path.write_text(binding_yaml(connection), encoding="utf-8")
    else:
        binding_path.unlink(missing_ok=True)
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
    for name in missing_fixtures:
        typer.echo(
            f"Add {name} to {out_dir / export_layout.FIXTURES} before you run. "
            "A Test Case uses this file."
        )
    if connection is not None:
        typer.echo(f"Wrote {binding_path}")
    typer.echo(
        f"Run with: metis engine run --input-dir {shlex.quote(str(out_dir / export_layout.OUTPUTS))}"
    )
    typer.echo("\nModel settings for the run (see docs/guide/models.md):")
    for line in _run_settings(specification):
        typer.echo(line)
    typer.echo(
        "To change a model, set USER_AGENT_MODEL or JUDGE_MODEL in .env, "
        "or edit specification.yaml."
    )
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


def _load_env() -> Path | None:
    """Read the one project `.env` (`metis.core.model_settings.load_env`).

    Exported values win: a `.env` fills gaps. Returns the file that was read, so a command can
    say where its settings came from. Exits when `METIS_ENV_FILE` names a missing file.
    """
    from metis.core.model_settings import ModelSettingsError, load_env

    try:
        return load_env()
    except ModelSettingsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _run_settings(specification: Specification) -> list[str]:
    """One line for each role that the run needs, with its model and status.

    The wizard writes a Specification without the simulator and judge keys. This list says
    which settings `metis engine run` needs. It shows variable names, never values.
    """
    import os

    from metis.core.model_settings import ROLES, ModelRole, resolve_role

    defaults = specification.experiment.defaults
    user_agent = resolve_role(
        ModelRole.USER_AGENT, os.environ, defaults.user_agent_model
    )
    run_roles = [user_agent]
    if specification.experiment.target_binding is not None:
        # As in the engine, the runner agent defaults to the user agent model of the run.
        run_roles.append(
            resolve_role(
                ModelRole.RUNNER_AGENT,
                os.environ,
                defaults.runner_agent_model,
                default=user_agent.model,
            )
        )
    run_roles.append(resolve_role(ModelRole.JUDGE, os.environ, defaults.judge_model))
    lines = []
    for settings in run_roles:
        role = settings.role
        status = (
            "configured"
            if settings.configured
            else f"not configured: set {' or '.join(ROLES[role].key_vars)}"
        )
        lines.append(
            f"  {ROLES[role].label}: {settings.model} from {settings.source} ({status})"
        )
    return lines


# ── commands ───────────────────────────────────────────────────────────────


@app.command()
def init(
    description: str = typer.Argument(
        ..., help="A raw description of the target or agent to evaluate."
    ),
    out_dir: Path | None = typer.Option(
        None,
        "--out-dir",
        help="Experiment root. Default: experiments/design/YYYYMMDD-HHMMSS-interview/.",
    ),
    restart: bool = typer.Option(
        False,
        "--restart",
        help="Discard an interview already in progress and start over.",
    ),
    documents: list[Path] | None = typer.Option(
        None,
        "--document",
        "-d",
        exists=True,
        dir_okay=False,
        readable=True,
        help="A file for the Interview to read. Repeat the option to add more files.",
    ),
    mode: Mode | None = typer.Option(
        None,
        "--mode",
        help="spec: write a Specification only. run: also connect the target. "
        "A terminal asks when this is not given; otherwise the mode is spec.",
    ),
    binding: Path | None = typer.Option(
        None,
        "--binding",
        help="A target binding YAML file to check and use. Implies --mode run.",
    ),
) -> None:
    """Start a new interview."""
    # Refuse before anything else — the filesystem check costs no model call and needs no
    # credentials, so an accidental re-run of `init` reports the collision rather than
    # overwriting an interview in progress. `--restart` is the one way past this.
    if out_dir is None:
        out_dir = Path("experiments/design") / export_layout.experiment_name(
            "interview"
        )
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
            f"  metis wizard resume --out-dir {shlex.quote(str(out_dir))}\n"
            f"  metis wizard init <description> --out-dir {shlex.quote(str(out_dir))} --restart",
            err=True,
        )
        raise typer.Exit(1)
    _require_binding_without_terminal(mode, binding)

    # Read the documents before the credential check, so a bad file costs no model call.
    from metis.wizard.adapters.cli.documents import (
        copy_opening_documents,
        read_opening_documents,
    )

    document_paths = documents or []
    opening_documents = read_opening_documents(
        document_paths,
        # File names are plain text, so Rich must not read brackets in them as markup.
        out=lambda line: console.print(line, markup=False, highlight=False),
        confirm=_confirm if sys.stdin.isatty() else None,
    )

    env_file = _load_env()
    if env_file is not None:
        typer.echo(f"Read settings from {env_file}")

    try:
        # Checked before anything else happens, so a missing key costs nothing and is
        # reported as the environment problem it is.
        interviewer = _new_interviewer()
    except InterviewerUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    _warn_without_embeddings()

    # The mode comes first, so a user who wants to run evals sees how to connect the target
    # before the Interview questions.
    connection, connection_skipped = _read_connection(mode, binding)

    from metis.wizard.adapters.cli.opening import read_capability_evidence

    known_capability_ids, capability_confidence = read_capability_evidence(
        out=console.print
    )
    # Keep the original bytes, so `resume` can put an opening file in the fixture folder.
    copy_opening_documents(
        document_paths,
        out_dir / export_layout.DOCUMENTS,
        out_dir / export_layout.FIXTURES,
    )
    typer.echo(
        f"Resume with: metis wizard resume --out-dir {shlex.quote(str(out_dir))}"
    )
    state = _drive(
        InterviewStartRequest(
            description=description,
            known_capability_ids=known_capability_ids,
            capability_confidence=capability_confidence,
            documents=opening_documents,
            connection=connection,
        ),
        interviewer=interviewer,
        matcher=_matcher(interviewer),
        out_dir=out_dir,
        console=console,
    )
    _write_outputs(state, out_dir, connection_skipped=connection_skipped)


def _terminal() -> bool:
    """Whether a user can answer questions about the target connection."""
    return sys.stdin.isatty()


def _require_binding_without_terminal(mode: Mode | None, binding: Path | None) -> None:
    """Stop run mode early when there is no terminal to ask for the binding values."""
    if mode is Mode.RUN and binding is None and not _terminal():
        typer.echo(
            "Error: run mode needs a target binding, and there is no terminal to ask for "
            "it. Pass --binding PATH.",
            err=True,
        )
        raise typer.Exit(1)


def _read_connection(
    mode: Mode | None, binding: Path | None
) -> tuple[TargetConnection | None, bool]:
    """Read the target connection for `init`. Returns it and whether run mode got no binding.

    With no `--mode`, a terminal asks for the mode; with no terminal, the mode is spec-only.
    """
    from metis.wizard.adapters.cli.connection import (
        load_binding_file,
        read_binding_source,
        read_mode,
        read_target_connection,
    )

    terminal = _terminal()
    if mode is None:
        if binding is not None:
            mode = Mode.RUN
        elif terminal:
            mode = Mode(read_mode(out=console.print))
        else:
            mode = Mode.SPEC
    if mode is Mode.SPEC:
        return None, False
    _require_binding_without_terminal(mode, binding)
    if binding is None:
        binding = read_binding_source(out=console.print)
    values = None
    if binding is not None:
        try:
            values = load_binding_file(binding)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            # name the file only: the YAML error can quote a line of the file
            typer.echo(
                f"Error: cannot read the target binding {binding} ({type(exc).__name__}).",
                err=True,
            )
            raise typer.Exit(1) from None
    connection = read_target_connection(
        out=console.print,
        values=values,
        # a binding file with no terminal is checked once; nothing is asked
        interactive=terminal,
    )
    return connection, connection is None


@app.command()
def resume(
    out_dir: Path = typer.Option(
        ...,
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

    env_file = _load_env()
    if env_file is not None:
        typer.echo(f"Read settings from {env_file}")

    try:
        interviewer = _new_interviewer()
    except InterviewerUnavailable as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    _warn_without_embeddings()

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


@app.command()
def connect(
    out_dir: Path = typer.Option(
        ...,
        "--out-dir",
        help="The experiment root holding inputs/interview_state.json.",
    ),
    binding: Path | None = typer.Option(
        None,
        "--binding",
        help="A target binding YAML file to check and use. Without it, the CLI asks.",
    ),
) -> None:
    """Add or replace the target connection of an Interview.

    A completed export is written again with the binding. An Interview in progress keeps the
    connection, and `resume` writes the binding when the Interview is complete.
    """
    path = _state_path(out_dir)
    if not path.is_file():
        typer.echo(f"Error: no interview at {path}.", err=True)
        raise typer.Exit(1)
    complete = (out_dir / export_layout.SPECIFICATION).is_file()
    state = _load(out_dir)

    env_file = _load_env()
    if env_file is not None:
        typer.echo(f"Read variables from {env_file}")
    connection, _ = _read_connection(Mode.RUN, binding)
    if connection is None:
        typer.echo("Error: no valid target binding. Nothing was changed.", err=True)
        raise typer.Exit(1)

    state = set_connection(state, connection)
    if complete:
        _write_outputs(state, out_dir)
    else:
        _save(state, out_dir)
        typer.echo(
            "Saved the connection. Resume with: "
            f"metis wizard resume --out-dir {shlex.quote(str(out_dir))}"
        )
