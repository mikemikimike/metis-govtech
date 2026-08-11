"""What the commands wire up.

Every other test builds a `StepDriver` by hand, so none of them noticed that the CLI built one
without a matcher. That gap is exactly the kind a unit test cannot see: each part worked, and
the assembly was wrong. These tests assert the assembly.
"""

import pytest
from fixtures.profiles import research_assistant

from metis.wizard.adapters.cli import commands as cli
from metis.wizard.adapters.llm.gateway import API_KEY_VAR, BASE_URL_VAR
from metis.wizard.application.compile import compile_experiment
from metis.wizard.application.matching import GENERATED_JUDGE_FQN, EmbeddingMatcher


class StubInterviewer:
    """Stands in for the gateway. Serves both roles, as the real one does."""

    def embed(self, texts: list[str], model: str = "") -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class RecordingConsole:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def status(self, message: str, *, spinner: str):
        self.messages.append((message, spinner))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class StatusSession:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def busy_message(self) -> str:
        return "Writing testable criteria…"

    def next(self) -> str:
        self.calls.append("next")
        return "request"

    def respond(self, response: object) -> None:
        self.calls.append(response)


def test_both_halves_of_the_cli_corridor_use_package_status_copy() -> None:
    session = StatusSession()
    console = RecordingConsole()

    assert cli._next_with_status(session, console) == "request"
    cli._respond_with_status(session, "response", console)

    assert console.messages == [
        ("Writing testable criteria…", "dots"),
        ("Writing testable criteria…", "dots"),
    ]
    assert session.calls == ["next", "response"]


def test_the_cli_wires_a_matcher() -> None:
    """Without one, every criterion keeps metric_fqn=None and the experiment measures
    almost nothing the user chose."""
    driver = cli._driver(StubInterviewer())

    assert driver.matcher is not None
    assert isinstance(driver.matcher, EmbeddingMatcher)


def test_the_cli_passes_one_session_id_to_the_interviewer_and_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from fixtures.scripted import ScriptedInterviewer
    from typer.testing import CliRunner

    from metis.wizard.bootstrap import create_cli_app

    seen: list[str | None] = []
    sessions = []

    def factory(session_id: str | None):
        seen.append(session_id)
        return ScriptedInterviewer()

    monkeypatch.setattr(cli, "_run", lambda session, out_dir: sessions.append(session))
    result = CliRunner().invoke(
        create_cli_app(factory),
        ["init", "--out-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert len(seen) == 1
    assert seen[0] is not None
    assert len(sessions) == 1
    assert sessions[0].state.id == seen[0]


def test_the_matcher_uses_the_same_gateway() -> None:
    """One endpoint and one key serve chat and embeddings, so the interviewer is the
    embedder — there is no second integration to configure."""
    interviewer = StubInterviewer()

    driver = cli._driver(interviewer)

    assert driver.matcher.embedder is interviewer  # type: ignore[attr-defined]


def test_an_unmatched_profile_loses_the_users_metrics() -> None:
    """The failure the wiring prevents, stated as a fact rather than a warning.

    This is what a real run produced before `_driver` existed: a file that validates and
    loads, and measures nothing at all.
    """
    profile = research_assistant()
    for behaviour in profile.ticked():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None  # what the driver leaves behind with no matcher

    document = compile_experiment(profile, "unmatched")

    assert all(t["metric_refs"] == [] for t in document["scenarios"])


def test_a_matched_profile_keeps_them() -> None:
    """The same profile, matched — every scenario carries the metrics its behaviours earned."""
    from metis.wizard.application.matching import match_profile

    profile = research_assistant()
    for behaviour in profile.ticked():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None

    match_profile(profile, cli._driver(StubInterviewer()).matcher)  # type: ignore[arg-type]
    document = compile_experiment(profile, "matched")

    # the stub embeds everything identically, so matches land on the fallback or a real
    # metric — either way every scenario ends up measured by something, which is the whole
    # difference from the unmatched case above.
    for scenario in document["scenarios"]:
        assert scenario["metric_refs"]
    assert all(
        ref for scenario in document["scenarios"] for ref in scenario["metric_refs"]
    )


def test_every_criterion_ends_up_measured_by_something() -> None:
    """A criterion with no metric is a criterion nothing checks. There should be none."""
    from metis.wizard.application.matching import match_profile

    profile = research_assistant()
    for behaviour in profile.ticked():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None

    match_profile(profile, cli._driver(StubInterviewer()).matcher)  # type: ignore[arg-type]

    for behaviour in profile.ticked():
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

    (tmp_path / "session.json").write_text("{}")  # so resume gets past its file check
    # `init` refuses outright when a session already exists — its own guard, checked before
    # credentials — so `--restart` is needed to reach the credential check this test is about.
    invocations = {
        "init": ["init", "--out-dir", str(tmp_path), "--restart"],
        "resume": ["resume", "--out-dir", str(tmp_path)],
    }
    for argv in invocations.values():
        result = runner.invoke(app, argv)

        assert result.exit_code == 1
        assert BASE_URL_VAR in result.output


# ── the init guard ───────────────────────────────────────────────────────────


def test_init_refuses_when_a_session_already_exists(tmp_path) -> None:
    """A re-run of `init` reports the collision rather than overwriting an interview.

    The check reads the filesystem only and runs before the interviewer is built, so it fires
    even with no credentials — which is what makes it a safe guard rather than a lucky one.
    """
    from typer.testing import CliRunner

    from metis.wizard.bootstrap import create_cli_app

    original = '{"do not": "overwrite me"}'
    (tmp_path / "session.json").write_text(original)

    result = CliRunner().invoke(create_cli_app(), ["init", "--out-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "already in progress" in result.output
    assert str(tmp_path / "session.json") in result.output
    # both ways forward are named
    assert "resume" in result.output
    assert "--restart" in result.output
    # and the existing session is untouched
    assert (tmp_path / "session.json").read_text() == original


def test_init_rejects_the_removed_name_option(tmp_path) -> None:
    from typer.testing import CliRunner

    from metis.wizard.bootstrap import create_cli_app

    result = CliRunner().invoke(
        create_cli_app(), ["init", "--out-dir", str(tmp_path), "--name", "X"]
    )

    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


# ── reading .env ───────────────────────────────────────────────────────────


def test_env_search_never_leaves_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """`load_dotenv()` with no arguments walks up past the repo and reads `~/.env`.

    Reading a credentials file from outside the project because nothing inside matched is
    not a default worth having, so the search is an explicit in-project list.
    """
    from pathlib import Path

    repo_root = Path(cli.__file__).resolve().parents[5]

    for loaded in cli._load_env():
        assert repo_root in loaded.parents, f"{loaded} is outside the project"


def test_a_real_environment_variable_wins_over_a_dotenv_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A .env fills gaps; it does not override something exported deliberately."""
    monkeypatch.setenv(BASE_URL_VAR, "https://exported.example")

    cli._load_env()

    import os

    assert os.environ[BASE_URL_VAR] == "https://exported.example"
