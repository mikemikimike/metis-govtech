"""The complete terminal corridor through the real Typer app, with no network."""

from pathlib import Path

from typer.testing import CliRunner

from metis.wizard import compile_specification
from metis.wizard.bootstrap import create_cli_app
from metis.wizard.contracts import InterviewState, Specification
from tests.fixtures.wizard.scripted import ScriptedInterviewer


def test_init_happy_path_writes_specification_and_review(
    tmp_path: Path,
) -> None:
    app = create_cli_app(ScriptedInterviewer)
    # Two model questions, keep every behaviour measured and continue,
    # continue through criteria, accept personas, then continue through scenarios.
    answers = [
        "",
        "low",
        "answer",
        "answer",
        "7",
        "14",
        "1",
        "21",
    ]

    result = CliRunner().invoke(
        app,
        ["init", "A research assistant", "--out-dir", str(tmp_path)],
        input="\n".join(answers) + "\n",
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "outputs/review.md").is_file()
    specification_path = tmp_path / "outputs/specification.yaml"
    assert specification_path.is_file()
    # The specification the engine's verdict report reads is valid YAML that loads back.
    assert Specification.load(specification_path).trial_count() > 0
    assert "Wrote" in result.output

    state = InterviewState.model_validate_json(
        (tmp_path / "inputs/interview_state.json").read_text()
    )
    assert (
        specification_path.read_text()
        == compile_specification(state.specification).specification_yaml
    )
    assert (tmp_path / "outputs/fixtures").is_dir()
    resumed = CliRunner().invoke(app, ["resume", "--out-dir", str(tmp_path)])
    assert resumed.exit_code == 0, resumed.output
    assert "complete" in resumed.output
