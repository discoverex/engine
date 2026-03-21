from __future__ import annotations

import subprocess
from pathlib import Path

import typer

app = typer.Typer(
    help="Embedded worker lifecycle commands",
    no_args_is_help=True,
    add_completion=False,
)
fixed_app = typer.Typer(no_args_is_help=True, add_completion=False)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = REPO_ROOT / "infra" / "worker"
FIXED_ENV = WORKER_DIR / ".env.fixed"
FIXED_ENV_EXAMPLE = WORKER_DIR / ".env.fixed.example"
FIXED_COMPOSE = WORKER_DIR / "docker-compose.fixed.yml"


def _compose_fixed(args: list[str]) -> int:
    cmd = ["docker", "compose"]
    if FIXED_ENV.exists():
        cmd.extend(["--env-file", str(FIXED_ENV)])
    cmd.extend(["-f", str(FIXED_COMPOSE), *args])
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    return int(proc.returncode)


def _ensure_runtime_dirs() -> None:
    runtime_root = REPO_ROOT / "runtime" / "worker"
    if FIXED_ENV.exists():
        for line in FIXED_ENV.read_text(encoding="utf-8").splitlines():
            if not line.startswith("WORKER_RUNTIME_DIR="):
                continue
            raw = line.split("=", 1)[1].strip()
            if not raw:
                break
            candidate = Path(raw).expanduser()
            runtime_root = (
                candidate if candidate.is_absolute() else (REPO_ROOT / candidate)
            )
            break
    for path in (
        runtime_root,
        runtime_root / "cache",
        runtime_root / "cache" / "models",
        runtime_root / "cache" / "uv",
        runtime_root / "checkpoints",
    ):
        path.mkdir(parents=True, exist_ok=True)


@app.command("init")
def init_worker_env() -> None:
    if FIXED_ENV.exists():
        typer.echo(str(FIXED_ENV))
        return
    FIXED_ENV.write_text(FIXED_ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    typer.echo(str(FIXED_ENV))


@fixed_app.command("up")
def fixed_up(build: bool = typer.Option(True, "--build/--no-build")) -> None:
    _ensure_runtime_dirs()
    args = ["up", "-d"]
    if build:
        args.append("--build")
    raise typer.Exit(_compose_fixed(args))


@fixed_app.command("down")
def fixed_down() -> None:
    raise typer.Exit(_compose_fixed(["down"]))


@fixed_app.command("ps")
def fixed_ps() -> None:
    raise typer.Exit(_compose_fixed(["ps"]))


@fixed_app.command("logs")
def fixed_logs(
    tail: int = typer.Option(120, "--tail"),
    follow: bool = typer.Option(False, "-f", "--follow"),
) -> None:
    args = ["logs", f"--tail={tail}"]
    if follow:
        args.append("-f")
    raise typer.Exit(_compose_fixed(args))


@fixed_app.command("build")
def fixed_build() -> None:
    raise typer.Exit(_compose_fixed(["build", "worker"]))


app.add_typer(fixed_app, name="fixed")
