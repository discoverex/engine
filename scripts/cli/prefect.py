from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import typer

from infra.register.branch_deployments import (
    DEFAULT_FLOW_KIND,
    SUPPORTED_FLOW_KINDS,
    deployment_name_for_branch,
)

app = typer.Typer(
    help="Prefect flow management and job registration",
    no_args_is_help=True,
    add_completion=False,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra" / "register"
DEFAULT_REGISTER_JOB_SPEC = (
    INFRA_DIR / "job_specs" / "real-generate-sdxl-gpu-8gb.json"
)


def _flow_kind_for_command(command: str) -> str:
    return {
        "gen-verify": DEFAULT_FLOW_KIND,
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _run_infra_script(script_name: str, args: list[str]) -> int:
    script_path = INFRA_DIR / script_name
    if not script_path.exists():
        typer.secho(f"Error: Script not found at {script_path}", fg=typer.colors.RED)
        return 1
    import sys

    cmd = [sys.executable, str(script_path)] + args
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def _extract_option(args: list[str], option: str) -> tuple[str | None, list[str]]:
    remaining: list[str] = []
    idx = 0
    value: str | None = None
    while idx < len(args):
        item = args[idx]
        if item == option:
            if idx + 1 >= len(args):
                raise typer.BadParameter(f"{option} requires a value")
            value = args[idx + 1]
            idx += 2
            continue
        prefix = f"{option}="
        if item.startswith(prefix):
            value = item[len(prefix) :]
            idx += 1
            continue
        remaining.append(item)
        idx += 1
    return value, remaining


def _contains_any(args: list[str], options: tuple[str, ...]) -> bool:
    for item in args:
        if item in options:
            return True
        if any(item.startswith(f"{option}=") for option in options):
            return True
    return False


@app.command(
    "deploy-flow",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Deploy a flow-kind-specific Prefect YAML deployment to the server.",
)
def deploy_flow(
    ctx: typer.Context,
    flow_kind: str = typer.Argument(..., help="One of: generate, verify, animate, combined."),
) -> None:
    if flow_kind not in SUPPORTED_FLOW_KINDS:
        raise typer.BadParameter(f"flow_kind must be one of: {', '.join(SUPPORTED_FLOW_KINDS)}")
    exit_code = _run_infra_script("deploy_prefect_flows.py", ["--flow-kind", flow_kind, *ctx.args])
    raise typer.Exit(exit_code)


@app.command(
    "register-flow",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Submit the standard job spec to a flow-kind-specific deployment.",
)
def register_flow(
    ctx: typer.Context,
    flow_kind: str = typer.Argument(..., help="One of: generate, verify, animate, combined."),
) -> None:
    if flow_kind not in SUPPORTED_FLOW_KINDS:
        raise typer.BadParameter(f"flow_kind must be one of: {', '.join(SUPPORTED_FLOW_KINDS)}")
    branch, remaining = _extract_option(ctx.args, "--branch")
    if not branch:
        typer.secho("Error: --branch is required.", fg=typer.colors.RED)
        raise typer.Exit(2)
    submit_args = [
        "--deployment",
        deployment_name_for_branch(branch, flow_kind=flow_kind),
        *remaining,
    ]
    if not _contains_any(remaining, ("--job-spec-file", "--job-spec-json")):
        submit_args.extend(["--job-spec-file", str(DEFAULT_REGISTER_JOB_SPEC)])
    exit_code = _run_infra_script("submit_job_spec.py", submit_args)
    raise typer.Exit(exit_code)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Compatibility alias for combined-flow deployment.",
)
def deploy(ctx: typer.Context) -> None:
    exit_code = _run_infra_script(
        "deploy_prefect_flows.py",
        ["--flow-kind", DEFAULT_FLOW_KIND, *ctx.args],
    )
    raise typer.Exit(exit_code)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Compatibility alias for combined-flow registration.",
)
def register(ctx: typer.Context) -> None:
    branch, remaining = _extract_option(ctx.args, "--branch")
    if not branch:
        typer.secho("Error: --branch is required.", fg=typer.colors.RED)
        raise typer.Exit(2)
    command, remaining = _extract_option(remaining, "--command")
    flow_kind: str = DEFAULT_FLOW_KIND
    if command:
        flow_kind = _flow_kind_for_command(command)
        remaining = ["--command", command, *remaining]
    submit_args = [
        "--deployment",
        deployment_name_for_branch(branch, flow_kind=flow_kind),
        *remaining,
    ]
    if not _contains_any(remaining, ("--job-spec-file", "--job-spec-json")):
        submit_args.extend(["--job-spec-file", str(DEFAULT_REGISTER_JOB_SPEC)])
    exit_code = _run_infra_script("submit_job_spec.py", submit_args)
    raise typer.Exit(exit_code)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Register a job using the raw orchestrator script.",
)
def register_raw(ctx: typer.Context) -> None:
    exit_code = _run_infra_script("register_orchestrator_job.py", ctx.args)
    raise typer.Exit(exit_code)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Build a job specification JSON file.",
)
def build_spec(ctx: typer.Context) -> None:
    exit_code = _run_infra_script("build_job_spec.py", ctx.args)
    raise typer.Exit(exit_code)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Submit a pre-built job specification to Prefect.",
)
def submit_spec(ctx: typer.Context) -> None:
    exit_code = _run_infra_script("submit_job_spec.py", ctx.args)
    raise typer.Exit(exit_code)


async def _fetch_logs(flow_run_id: str, limit: int = 1000) -> None:
    try:
        from prefect.client import get_client
        from prefect.logging.configuration import setup_logging
        
        # Ensure logging is set up to avoid unnecessary noise or missing info
        setup_logging()
        
        async with get_client() as client:
            # We need the UUID or string ID
            logs = await client.read_logs(flow_run_id=flow_run_id, limit=limit)
            if not logs:
                typer.echo(f"No logs found for flow run {flow_run_id}")
                return

            for log in logs:
                # Basic formatting
                color = typer.colors.WHITE
                if log.level >= 40: # ERROR
                    color = typer.colors.RED
                elif log.level >= 30: # WARNING
                    color = typer.colors.YELLOW
                elif log.level <= 10: # DEBUG
                    color = typer.colors.CYAN
                
                timestamp = log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                typer.echo(
                    typer.style(f"[{timestamp}] ", fg=typer.colors.BRIGHT_BLACK) +
                    typer.style(f"{log.name} | {log.level_name.ljust(7)} | ", fg=color) +
                    f"{log.message}"
                )
    except ImportError:
        typer.secho("Error: prefect library not found in current environment.", fg=typer.colors.RED)
    except Exception as e:
        typer.secho(f"Error fetching logs: {e}", fg=typer.colors.RED)


@app.command(help="Fetch and display logs for a specific Prefect flow run ID.")
def check_logs(
    flow_run_id: str = typer.Argument(..., help="The UUID of the flow run"),
    limit: int = typer.Option(1000, help="Maximum number of log entries to fetch"),
) -> None:
    asyncio.run(_fetch_logs(flow_run_id, limit))
