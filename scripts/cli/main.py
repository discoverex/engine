from __future__ import annotations

import typer

from . import artifacts, legacy, prefect, worker

app = typer.Typer(
    help="Discoverex Core Project Management CLI",
    no_args_is_help=True,
    add_completion=False,
)

# Register sub-apps
app.add_typer(prefect.app, name="prefect")
app.add_typer(legacy.app, name="legacy")
app.add_typer(worker.app, name="worker")
app.add_typer(artifacts.app, name="artifacts")

if __name__ == "__main__":
    app()
