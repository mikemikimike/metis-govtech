"""What the commands wire up.

Every other test drives the Interview through `handle_interview`, so none of them noticed whether the
CLI door wired a matcher onto its turns. That gap is exactly the kind a unit test cannot see: each
part worked, and the assembly was wrong. These tests assert the assembly the CLI door builds.
"""

import pytest
import typer

from metis.wizard.adapters.cli import commands as cli
from metis.wizard.adapters.llm.gateway import API_KEY_VAR, BASE_URL_VAR
from metis.wizard.application import config
from metis.wizard.application.compile import compile_experiment
from metis.wizard.application.matching import GENERATED_JUDGE_FQN, EmbeddingMatcher
from metis.wizard.contracts import ChoiceRequest, InterviewState, Option, OptionId
from metis.wizard.domain.permissions import InterviewStep
from tests.fixtures.wizard.context import interview_context
from tests.fixtures.wizard.specifications import research_assistant


class StubInterviewer:
    """Stands in for the gateway. Serves both roles, as the real one does."""

    def embed(self, texts: list[str], model: str = "") -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _state_pending_at(stage: InterviewStep) -> InterviewState:
    """A client-held state whose one pending screen was stamped at a given stage."""
    request = ChoiceRequest(
        prompt="Do these look right?",
        stage=stage,
        request_id="req-1",
        options=[Option(id=OptionId(action="accept"), label="Looks right")],
    )
    return InterviewState(
        specification=research_assistant(), context=interview_context(), pending=request
    )


def test_the_spinner_uses_the_package_status_copy_for_the_pending_stage() -> None:
    """The CLI door's spinner names the stage the turn is about to work on, in package copy.

    Before any state exists the turn opens at clarify; once a screen is pending, its own stage
    drives the copy. The door never authors this text — it reads the package status owner.
    """
    assert cli._busy_message(None) == config.status_for(InterviewStep.CLARIFY)
    assert cli._busy_message(
        _state_pending_at(InterviewStep.CRITERIA)
    ) == config.status_for(InterviewStep.CRITERIA)


def test_resume_reports_the_pending_request_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A pending request is authoritative even when Specification evidence points elsewhere."""
    from typer.testing import CliRunner

    from metis.wizard.adapters.cli import render as render_module
    from metis.wizard.bootstrap import create_cli_app

    state = _state_pending_at(InterviewStep.CRITERIA)
    (tmp_path / "interview_state.json").write_text(
        state.model_dump_json(), encoding="utf-8"
    )
    monkeypatch.setattr(cli, "_load_env", list)
    monkeypatch.setattr(cli, "_new_interviewer", StubInterviewer)

    def stop_after_heading(*_args, **_kwargs):
        raise RuntimeError("stop after resume heading")

    monkeypatch.setattr(render_module, "render", stop_after_heading)

    result = CliRunner().invoke(
        create_cli_app(), ["resume", "--out-dir", str(tmp_path)]
    )

    assert "Resuming at the criteria step." in result.output


def test_a_retryable_failure_is_resent_when_the_user_agrees(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The CLI acts on the `retryable` flag the contract exposes.

    A retryable failure leaves the state unchanged, so the door offers the same operation
    again — the terminal equivalent of the web client's Retry button — rather than treating
    every failure as terminal.
    """
    from rich.console import Console

    from metis.wizard import (
        InterviewErrorCode,
        InterviewFailure,
        InterviewStartRequest,
        InterviewSuccess,
    )

    start = InterviewStartRequest(
        description="a helpful research assistant",
        known_capability_ids=[],
        capability_confidence="low",
    )
    done = InterviewSuccess(
        state=InterviewState(
            specification=research_assistant(),
            context=interview_context(),
            confirmed=True,
        ),
        stage=InterviewStep.DONE,
        outcome="done",
    )
    seen: list[object] = []

    def fake_handle(request, **_kwargs):
        seen.append(request)
        if len(seen) == 1:
            return InterviewFailure(
                code=InterviewErrorCode.MODEL_UNAVAILABLE,
                message="The model could not be reached; nothing was changed.",
                retryable=True,
                state=None,
            )
        return done

    monkeypatch.setattr(cli, "handle_interview", fake_handle)
    monkeypatch.setattr(cli, "_retry_confirmed", lambda _failure: True)

    result = cli._drive(
        start,
        interviewer=StubInterviewer(),
        matcher=None,
        out_dir=tmp_path,
        console=Console(),
    )

    assert seen == [start, start]  # the failed start was resent unchanged
    assert result.confirmed is True


def test_a_non_retryable_failure_stops_without_offering_a_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A terminal failure exits at once; only a retryable one is ever offered again."""
    from rich.console import Console

    from metis.wizard import (
        InterviewErrorCode,
        InterviewFailure,
        InterviewStartRequest,
    )

    offered: list[object] = []
    monkeypatch.setattr(
        cli, "_retry_confirmed", lambda failure: offered.append(failure) or True
    )
    monkeypatch.setattr(
        cli,
        "handle_interview",
        lambda request, **_kwargs: InterviewFailure(
            code=InterviewErrorCode.COMPLETION_FAILED,
            message="I couldn't finish this into a runnable evaluation on my own.",
            retryable=False,
            state=None,
        ),
    )

    with pytest.raises(typer.Exit):
        cli._drive(
            InterviewStartRequest(
                description="x", known_capability_ids=[], capability_confidence="low"
            ),
            interviewer=StubInterviewer(),
            matcher=None,
            out_dir=tmp_path,
            console=Console(),
        )

    assert offered == []  # the retryable gate short-circuits before any prompt


def test_the_cli_wires_a_matcher() -> None:
    """Without one, every criterion keeps metric_fqn=None and the experiment measures
    almost nothing the user chose."""
    matcher = cli._matcher(StubInterviewer())

    assert isinstance(matcher, EmbeddingMatcher)


def test_the_matcher_uses_the_same_gateway() -> None:
    """One endpoint and one key serve chat and embeddings, so the interviewer is the
    embedder — there is no second integration to configure."""
    interviewer = StubInterviewer()

    matcher = cli._matcher(interviewer)

    assert matcher.embedder is interviewer  # type: ignore[attr-defined]


def test_an_unmatched_specification_loses_the_users_metrics() -> None:
    """The failure the wiring prevents, stated as a fact rather than a warning.

    Without a matcher every criterion keeps metric_fqn=None, and the result is a file that
    validates and loads, and measures nothing at all.
    """
    specification = research_assistant()
    for behaviour in specification.measured_behaviours():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None  # what a turn leaves behind with no matcher

    from metis.wizard.application.compile import CompilationError

    with pytest.raises(CompilationError, match="needs a Grader"):
        compile_experiment(specification, "unmatched")


def test_a_matched_specification_keeps_them() -> None:
    """The same specification, matched — every scenario carries the metrics its behaviours earned."""
    from metis.wizard.application.matching import match_specification

    specification = research_assistant()
    for behaviour in specification.measured_behaviours():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None

    match_specification(specification, cli._matcher(StubInterviewer()))  # type: ignore[arg-type]
    document = compile_experiment(specification, "matched")

    # the stub embeds everything identically, so matches land on the fallback or a real
    # metric — either way every scenario ends up measured by something, which is the whole
    # difference from the unmatched case above.
    assert all(task["criterion_refs"] for task in document["tasks"])


def test_every_criterion_ends_up_measured_by_something() -> None:
    """A criterion with no metric is a criterion nothing checks. There should be none."""
    from metis.wizard.application.matching import match_specification

    specification = research_assistant()
    for behaviour in specification.measured_behaviours():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None

    match_specification(specification, cli._matcher(StubInterviewer()))  # type: ignore[arg-type]

    for behaviour in specification.measured_behaviours():
        for criterion in behaviour.criteria:
            assert criterion.metric_fqn
            assert (
                criterion.metric_fqn == GENERATED_JUDGE_FQN
                or "Metric" in criterion.metric_fqn
            )


def test_both_commands_fail_before_any_call_without_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from typer.testing import CliRunner

    monkeypatch.delenv(BASE_URL_VAR, raising=False)
    monkeypatch.delenv(API_KEY_VAR, raising=False)
    # Isolate from any real `.env` in the project, which would otherwise supply exactly the
    # credentials this test is asserting the absence of.
    monkeypatch.setattr(cli, "_load_env", list)
    runner = CliRunner()
    from metis.wizard.bootstrap import create_cli_app

    app = create_cli_app()

    (tmp_path / "interview_state.json").write_text(
        "{}"
    )  # so resume gets past its file check
    # `init` refuses outright when an interview already exists — its own guard, checked before
    # credentials — so `--restart` is needed to reach the credential check this test is about.
    invocations = {
        "init": [
            "init",
            "A research assistant",
            "--out-dir",
            str(tmp_path),
            "--restart",
        ],
        "resume": ["resume", "--out-dir", str(tmp_path)],
    }
    for argv in invocations.values():
        result = runner.invoke(app, argv)

        assert result.exit_code == 1
        assert BASE_URL_VAR in result.output


# ── the init guard ───────────────────────────────────────────────────────────


def test_init_refuses_when_a_interview_already_exists(tmp_path) -> None:
    """A re-run of `init` reports the collision rather than overwriting an interview.

    The check reads the filesystem only and runs before the interviewer is built, so it fires
    even with no credentials — which is what makes it a safe guard rather than a lucky one.
    """
    from typer.testing import CliRunner

    from metis.wizard.bootstrap import create_cli_app

    original = '{"do not": "overwrite me"}'
    (tmp_path / "interview_state.json").write_text(original)

    result = CliRunner().invoke(
        create_cli_app(),
        ["init", "A research assistant", "--out-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert "already in progress" in result.output
    assert str(tmp_path / "interview_state.json") in result.output
    # both ways forward are named
    assert "resume" in result.output
    assert "--restart" in result.output
    # and the existing interview is untouched
    assert (tmp_path / "interview_state.json").read_text() == original


# ── reading .env ───────────────────────────────────────────────────────────


def test_a_real_environment_variable_wins_over_a_dotenv_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A .env fills gaps; it does not override something exported deliberately."""
    monkeypatch.setenv(BASE_URL_VAR, "https://exported.example")

    cli._load_env()

    import os

    assert os.environ[BASE_URL_VAR] == "https://exported.example"
