import typer
from metis.engine.cli import app as engine_app
from metis.wizard.cli import app as wizard_app

app = typer.Typer(
    name="metis",
    help="METIS — Measurement and Evaluation of Trustworthy Intelligent Systems.",
)
app.add_typer(engine_app, name="engine")
app.add_typer(wizard_app, name="wizard")
