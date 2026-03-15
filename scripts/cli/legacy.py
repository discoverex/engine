from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(
    help="Legacy scripts and utility wrappers",
    no_args_is_help=True,
    add_completion=False,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Run the legacy prompt-driven generation on CPU.",
)
def generate_cpu(ctx: typer.Context):
    script_path = SCRIPTS_DIR / "run_generate_cpu_sdxl.sh"
    if not script_path.exists():
        typer.secho(f"Error: Script not found at {script_path}", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Run the shell script
    cmd = ["bash", str(script_path)] + ctx.args
    proc = subprocess.run(cmd, check=False)
    raise typer.Exit(proc.returncode)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Check the contents of a MinIO scene bundle.",
)
def check_minio(ctx: typer.Context):
    script_path = SCRIPTS_DIR / "check_minio_scene_bundle.py"
    if not script_path.exists():
        typer.secho(f"Error: Script not found at {script_path}", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    # Run the python script
    cmd = [sys.executable, str(script_path)] + ctx.args
    proc = subprocess.run(cmd, check=False)
    raise typer.Exit(proc.returncode)
