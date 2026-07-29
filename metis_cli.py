from importlib.metadata import PackageNotFoundError, version

import typer
from metis.engine.cli import app as engine_app
from metis.wizard.cli import app as wizard_app

try:
    __version__ = version("metis")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"


def version_callback(value: bool):
    if value:
        typer.echo(f"metis {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="metis",
    help="METIS — Measurement and Evaluation of Trustworthy Intelligent Systems.",
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True
    ),
):
    pass


app.add_typer(engine_app, name="engine")
app.add_typer(wizard_app, name="wizard")
