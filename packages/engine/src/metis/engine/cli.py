import typer
from metis.engine import __version__, core_version

app = typer.Typer(help="Run METIS evaluations against traces.")


def version_callback(value: bool):
    if value:
        typer.echo(f"metis-engine {__version__} (core {core_version})")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True
    ),
):
    typer.echo(f"Hello from metis-engine {__version__}")
