"""The complete terminal corridor through the real Typer app, with no network."""

from pathlib import Path

from typer.testing import CliRunner

from metis.wizard.bootstrap import create_cli_app
from metis.wizard.contracts import ProductProfile
from tests.fixtures.wizard.scripted import ScriptedInterviewer


def test_init_happy_path_writes_experiment_review_and_profile(tmp_path: Path) -> None:
    app = create_cli_app(ScriptedInterviewer)
    # Two model questions, keep every behaviour measured and continue,
    # continue through criteria, accept personas, then continue through scenarios.
    answers = ["", "low", "answer", "answer", "7", "11", "1", "9"]

    result = CliRunner().invoke(
        app,
        ["init", "A research assistant", "--out-dir", str(tmp_path)],
        input="\n".join(answers) + "\n",
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "experiment.yaml").is_file()
    assert (tmp_path / "review.md").is_file()
    profile_path = tmp_path / "profile.yaml"
    assert profile_path.is_file()
    # The profile the engine's verdict report reads is valid YAML that loads back.
    assert ProductProfile.load(profile_path).trial_count() > 0
    assert "Wrote" in result.output
