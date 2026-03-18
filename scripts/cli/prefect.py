from __future__ import annotations

import asyncio
import csv
import json
import subprocess
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import typer
import yaml

from infra.register.branch_deployments import (
    DEFAULT_FLOW_KIND,
    SUPPORTED_FLOW_KINDS,
    deployment_name_for_branch,
    experiment_deployment_name,
)


@runtime_checkable
class PrefectLog(Protocol):
    level: int
    message: str
    timestamp: datetime
    name: str


app = typer.Typer(
    help="Prefect flow management and job registration",
    no_args_is_help=True,
    add_completion=False,
)
deploy_app = typer.Typer(no_args_is_help=True, add_completion=False)
register_app = typer.Typer(no_args_is_help=True, add_completion=False)

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra" / "register"
DEFAULT_REGISTER_JOB_SPEC = (
    INFRA_DIR
    / "job_specs"
    / "real-generate-pixart-hidden-object-naturalness-v2-8gb-safe.yaml"
)
DEFAULT_NATURALNESS_SWEEP_SPEC = (
    INFRA_DIR / "sweeps" / "naturalness_medium.yaml"
)
DEFAULT_EXPERIMENT_QUEUE = "gpu-fixed-batch"
DEFAULT_EXPERIMENT_NAME = "naturalness"


def _flow_kind_for_command(command: str) -> str:
    return {
        "gen-verify": DEFAULT_FLOW_KIND,
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _experiment_deployment_name(branch: str, experiment: str) -> str:
    return experiment_deployment_name(branch, experiment=experiment)


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


def _load_job_spec_template(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"job spec at {path} must decode to an object")
    return payload


def _row_value(row: Mapping[str, str], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _build_job_spec_json_for_row(
    template: Mapping[str, Any],
    row: Mapping[str, str],
    *,
    row_index: int,
) -> str:
    job_spec = deepcopy(dict(template))
    inputs = job_spec.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        raise typer.BadParameter("job spec inputs must decode to an object")
    args = inputs.setdefault("args", {})
    if not isinstance(args, dict):
        raise typer.BadParameter("job spec inputs.args must decode to an object")

    required_columns = ("background_prompt", "object_prompt")
    missing = [column for column in required_columns if not _row_value(row, column)]
    if missing:
        columns = ", ".join(missing)
        raise typer.BadParameter(f"csv row {row_index} missing required column(s): {columns}")

    args["background_prompt"] = _row_value(row, "background_prompt")
    args["object_prompt"] = _row_value(row, "object_prompt")
    args["background_negative_prompt"] = (
        _row_value(row, "background_negative_prompt")
        or str(args.get("background_negative_prompt", ""))
    )
    args["object_negative_prompt"] = (
        _row_value(row, "object_negative_prompt")
        or str(args.get("object_negative_prompt", ""))
    )
    args["final_prompt"] = _row_value(row, "final_prompt") or str(
        args.get("final_prompt", "")
    )
    args["final_negative_prompt"] = _row_value(row, "final_negative_prompt") or str(
        args.get("final_negative_prompt", "")
    )

    row_job_name = _row_value(row, "job_name")
    if row_job_name:
        job_spec["job_name"] = row_job_name
    elif "job_name" not in job_spec:
        job_spec["job_name"] = f"batch-generate-{row_index:03d}"

    return json.dumps(job_spec, ensure_ascii=True)


def _prefect_client_settings() -> Mapping[Any, Any]:
    from prefect.settings import (
        PREFECT_API_URL,
        PREFECT_CLIENT_CUSTOM_HEADERS,
    )

    from infra.register.settings import SETTINGS

    api_url = SETTINGS.prefect_api_url or "https://prefect-api.discoverex.qzz.io/api"
    headers: dict[str, str] = {}
    client_id = (
        SETTINGS.prefect_cf_access_client_id or SETTINGS.cf_access_client_id
    ).strip()
    client_secret = (
        SETTINGS.prefect_cf_access_client_secret or SETTINGS.cf_access_client_secret
    ).strip()
    if client_id and client_secret:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret
    return {
        PREFECT_API_URL: api_url,
        PREFECT_CLIENT_CUSTOM_HEADERS: headers,
    }


def _build_prefect_log_filter(flow_run_id: str) -> Any:
    from prefect.client.schemas.filters import LogFilter, LogFilterFlowRunId

    return LogFilter(flow_run_id=LogFilterFlowRunId(any_=[UUID(flow_run_id)]))


async def _read_prefect_logs(flow_run_id: str, limit: int) -> list[PrefectLog]:
    from prefect.client.orchestration import get_client
    from prefect.settings import temporary_settings

    # Using Any for settings mapping as PREFECT_API_URL/PREFECT_CLIENT_CUSTOM_HEADERS 
    # are complex objects not easily typed here.
    with temporary_settings(updates=_prefect_client_settings()):
        async with get_client() as client:
            logs = await client.read_logs(
                log_filter=_build_prefect_log_filter(flow_run_id),
                limit=limit,
            )
    # Prefect Log objects usually satisfy PrefectLog protocol
    return list(logs)  # type: ignore


async def _describe_flow_run_tree(flow_run_id: str, depth: int = 2) -> list[str]:
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.filters import (
        FlowRunFilter,
        FlowRunFilterId,
        TaskRunFilter,
        TaskRunFilterFlowRunId,
    )
    from prefect.settings import temporary_settings

    async def _visit(client: Any, run_id: UUID, level: int) -> list[str]:
        flow_run = await client.read_flow_run(run_id)
        flow_obj = await client.read_flow(flow_run.flow_id)
        task_runs = list(
            await client.read_task_runs(
                task_run_filter=TaskRunFilter(
                    flow_run_id=TaskRunFilterFlowRunId(any_=[flow_run.id])
                ),
                limit=100,
            )
        )
        lines = [
            (
                f"{'  ' * level}flow {flow_obj.name} "
                f"[{flow_run.state_name}] id={flow_run.id} tasks={len(task_runs)}"
            )
        ]
        if level >= depth:
            return lines

        parent_task_ids = [task_run.id for task_run in task_runs]
        child_runs: list[Any] = []
        if parent_task_ids:
            child_runs = list(
                await client.read_flow_runs(
                    flow_run_filter=FlowRunFilter(parent_task_run_id={"any_": parent_task_ids}),
                    limit=100,
                )
            )

        child_run_by_parent_task = {
            child_run.parent_task_run_id: child_run for child_run in child_runs
        }

        for task_run in task_runs:
            child_run = child_run_by_parent_task.get(task_run.id)
            child_suffix = ""
            if child_run is not None:
                child_suffix = f" child_flow={child_run.id}"
            lines.append(
                (
                    f"{'  ' * (level + 1)}task {task_run.name} "
                    f"[{task_run.state_name}] id={task_run.id}{child_suffix}"
                )
            )
            if child_run is not None:
                lines.extend(await _visit(client, child_run.id, level + 2))
        return lines

    with temporary_settings(updates=_prefect_client_settings()):
        async with get_client() as client:
            return await _visit(client, UUID(flow_run_id), 0)


@deploy_app.command(
    "flow",
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


@register_app.command(
    "flow",
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


@register_app.command(
    "batch",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Submit one flow run per CSV row using the default job spec as a template.",
)
def register_batch(
    ctx: typer.Context,
    csv_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    flow_kind: str = typer.Option("generate", "--flow-kind", help="One of: generate, verify, animate, combined."),
    job_spec_file: Path = typer.Option(
        DEFAULT_REGISTER_JOB_SPEC,
        "--job-spec-file",
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Template job spec file used as the base payload for each row.",
    ),
) -> None:
    if flow_kind not in SUPPORTED_FLOW_KINDS:
        raise typer.BadParameter(f"flow_kind must be one of: {', '.join(SUPPORTED_FLOW_KINDS)}")
    branch, remaining = _extract_option(ctx.args, "--branch")
    if not branch:
        typer.secho("Error: --branch is required.", fg=typer.colors.RED)
        raise typer.Exit(2)
    if _contains_any(remaining, ("--job-spec-file", "--job-spec-json")):
        raise typer.BadParameter("register batch manages job spec payloads internally")

    template = _load_job_spec_template(job_spec_file)
    deployment = deployment_name_for_branch(branch, flow_kind=flow_kind)
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
    if not rows:
        raise typer.BadParameter(f"csv file {csv_path} has no data rows")

    for row_index, row in enumerate(rows, start=1):
        submit_args = [
            "--deployment",
            deployment,
            *remaining,
            "--job-spec-json",
            _build_job_spec_json_for_row(template, row, row_index=row_index),
        ]
        exit_code = _run_infra_script("submit_job_spec.py", submit_args)
        if exit_code != 0:
            raise typer.Exit(exit_code)


@register_app.command(
    "experiment-sweep",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Submit an experiment sweep using a YAML sweep spec.",
)
def register_experiment_sweep(
    ctx: typer.Context,
    experiment: str = typer.Option(DEFAULT_EXPERIMENT_NAME, "--experiment"),
    sweep_spec: Path = typer.Option(
        DEFAULT_NATURALNESS_SWEEP_SPEC,
        "--sweep-spec",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    branch, remaining = _extract_option(ctx.args, "--branch")
    submit_args = [str(sweep_spec)]
    if branch:
        submit_args.extend(["--deployment", _experiment_deployment_name(branch, experiment)])
        submit_args.extend(["--branch", branch])
    submit_args.extend(["--experiment", experiment])
    submit_args.extend(remaining)
    exit_code = _run_infra_script(
        "naturalness_sweep.py",
        submit_args,
    )
    raise typer.Exit(exit_code)


@deploy_app.command(
    "experiment",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Deploy an experiment generate runner to the batch queue.",
)
def deploy_experiment(
    ctx: typer.Context,
    experiment: str = typer.Option(DEFAULT_EXPERIMENT_NAME, "--experiment"),
) -> None:
    branch, remaining = _extract_option(ctx.args, "--branch")
    deploy_args = [
        "--flow-kind",
        "generate",
        "--work-queue-name",
        DEFAULT_EXPERIMENT_QUEUE,
    ]
    if branch:
        deploy_args.extend(["--deployment-name", _experiment_deployment_name(branch, experiment)])
        deploy_args.extend(["--branch", branch])
    deploy_args.extend(remaining)
    exit_code = _run_infra_script(
        "deploy_prefect_flows.py",
        deploy_args,
    )
    raise typer.Exit(exit_code)


@app.command(
    "deploycombined",
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
    "registercombined",
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


@register_app.command(
    "raw",
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


async def _fetch_logs(flow_run_id: str, limit: int = 200) -> None:
    try:
        from prefect.logging.configuration import setup_logging

        setup_logging()
        logs = await _read_prefect_logs(flow_run_id, limit)
        if not logs:
            typer.echo(f"No logs found for flow run {flow_run_id}")
            return

        for log in logs:
            color = typer.colors.WHITE
            if log.level >= 40:
                color = typer.colors.RED
            elif log.level >= 30:
                color = typer.colors.YELLOW
            elif log.level <= 10:
                color = typer.colors.CYAN
            timestamp = log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            level_name = str(getattr(log, "level_name", getattr(log, "level", "")))
            logger_name = log.name
            typer.echo(
                typer.style(f"[{timestamp}] ", fg=typer.colors.BRIGHT_BLACK) +
                typer.style(f"{logger_name} | {level_name.ljust(7)} | ", fg=color) +
                f"{log.message}"
            )
    except ImportError:
        typer.secho("Error: prefect library not found in current environment.", fg=typer.colors.RED)
    except Exception as e:
        typer.secho(f"Error fetching logs: {e}", fg=typer.colors.RED)


@app.command(help="Fetch and display logs for a specific Prefect flow run ID.")
def check_logs(
    flow_run_id: str = typer.Argument(..., help="The UUID of the flow run"),
    limit: int = typer.Option(200, help="Maximum number of log entries to fetch"),
) -> None:
    asyncio.run(_fetch_logs(flow_run_id, limit))


@app.command("inspect-run", help="Display a flow run tree using Prefect API data.")
def inspect_run(
    flow_run_id: str = typer.Argument(..., help="The UUID of the root flow run"),
    depth: int = typer.Option(2, min=0, help="Nested flow depth to display"),
) -> None:
    lines = asyncio.run(_describe_flow_run_tree(flow_run_id, depth))
    for line in lines:
        typer.echo(line)


app.add_typer(deploy_app, name="deploy")
app.add_typer(register_app, name="register")
