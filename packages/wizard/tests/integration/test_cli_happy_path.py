"""The complete terminal corridor through the real Typer app, with no network."""

from pathlib import Path

from fixtures.scripted import ScriptedInterviewer
from typer.testing import CliRunner

from metis.wizard.bootstrap import create_cli_app


def test_init_happy_path_writes_both_outputs(tmp_path: Path) -> None:
    app = create_cli_app(lambda: ScriptedInterviewer())
    # Chat x2, accept the behaviour draft, select two behaviours, continue through
    # prioritise and criteria, accept personas, then continue through tasks.
    answers = ["answer", "answer", "1", "1,2", "5", "8", "1", "8"]

    result = CliRunner().invoke(
        app,
        ["init", "--out-dir", str(tmp_path)],
        input="\n".join(answers) + "\n",
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "experiment.yaml").is_file()
    assert (tmp_path / "review.md").is_file()
    assert "Wrote" in result.output
