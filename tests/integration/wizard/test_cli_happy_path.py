"""The complete terminal corridor through the real Typer app, with no network."""

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from metis.wizard import compile_specification
from metis.wizard.adapters.cli import commands
from metis.wizard.bootstrap import create_cli_app
from metis.wizard.contracts import InterviewState, Specification
from tests.fixtures.wizard.scripted import ScriptedInterviewer, ScriptedMatcher


@pytest.mark.parametrize("explicit", [False, True])
def test_init_happy_path_writes_specification_and_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit: bool,
    export_clock,
) -> None:
    # The scripted interviewer cannot embed, so the real matcher would fall back to the
    # generated judge, which no longer exists (grader redesign, #428). This test is about the
    # terminal corridor, not matching, so it uses the scripted matcher's runnable grader.
    monkeypatch.setattr(commands, "_matcher", lambda _interviewer: ScriptedMatcher())
    monkeypatch.chdir(tmp_path)
    root = (
        tmp_path / "chosen folder"
        if explicit
        else tmp_path / "experiments/design/20261016-223045-interview"
    )
    arguments = ["--out-dir", str(root)] if explicit else []
    app = create_cli_app(ScriptedInterviewer)
    # Two model questions, keep every behaviour measured and continue,
    # continue through criteria, accept personas, then continue through scenarios.
    answers = [
        "",
        "low",
        "answer",
        "answer",
        "8",
        "14",
        "2",
        "21",
    ]

    result = CliRunner().invoke(
        app,
        ["init", "A research assistant", *arguments],
        input="\n".join(answers) + "\n",
    )

    assert result.exit_code == 0, result.output
    assert (root / "outputs/review.md").is_file()
    specification_path = root / "outputs/specification.yaml"
    assert specification_path.is_file()
    # The specification the engine's verdict report reads is valid YAML that loads back.
    assert Specification.load(specification_path).trial_count() > 0
    assert "Wrote" in result.output

    state = InterviewState.model_validate_json(
        (root / "inputs/interview_state.json").read_text()
    )
    assert (
        specification_path.read_text()
        == compile_specification(state.specification).specification_yaml
    )
    assert (root / "outputs/fixtures").is_dir()
    collision = CliRunner().invoke(app, ["init", "A research assistant", *arguments])
    assert collision.exit_code == 1
    assert "complete" in collision.output
    if not explicit:
        export_clock(datetime(2026, 10, 16, 22, 30, 46))
        another = CliRunner().invoke(
            app, ["init", "A research assistant"], input="\n".join(answers) + "\n"
        )
        assert another.exit_code == 0, another.output
        assert (
            tmp_path
            / "experiments/design/20261016-223046-interview/outputs/specification.yaml"
        ).is_file()
        assert (
            specification_path.read_text()
            == compile_specification(state.specification).specification_yaml
        )
    export_clock(datetime(2026, 10, 17, 8, 15, 30))
    resumed = CliRunner().invoke(app, ["resume", "--out-dir", str(root)])
    assert resumed.exit_code == 0, resumed.output
    assert "complete" in resumed.output
    restarted = CliRunner().invoke(
        app,
        ["init", "A research assistant", "--out-dir", str(root), "--restart"],
        input="\n".join(answers) + "\n",
    )
    assert restarted.exit_code == 0, restarted.output
    assert Specification.load(specification_path).trial_count() > 0


def test_resume_requires_an_explicit_experiment_root() -> None:
    result = CliRunner().invoke(create_cli_app(ScriptedInterviewer), ["resume"])
    assert result.exit_code == 2
    assert "--out-dir" in result.output
