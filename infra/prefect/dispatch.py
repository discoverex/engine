from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prefect import get_run_logger
from prefect.client.orchestration import get_client
from prefect.context import FlowRunContext, TaskRunContext
from prefect.states import Pending

from infra.prefect.job_spec import (
    config_name,
    coerce_args,
    coerce_overrides,
    mapped_command,
    string_value,
)


@dataclass
class DispatchResult:
    payload: dict[str, Any]
    stdout: str
    stderr: str


def dispatch_engine_job(
    payload: dict[str, Any],
    *,
    cwd: Path,
    env: dict[str, str],
) -> DispatchResult:
    logger = get_run_logger()
    python_bin = cwd / ".venv" / "bin" / "python"
    if not python_bin.exists():
        raise RuntimeError(f"missing bootstrap python: {python_bin}")

    child_env = {**env, "ORCH_JOB_INPUTS_JSON": json.dumps(payload, ensure_ascii=True)}
    execute_cmd = [
        str(python_bin),
        "-m",
        "discoverex.application.flows.launcher_entry",
    ]

    child_flow_run_id = _create_child_flow_run(payload)
    if child_flow_run_id:
        child_env["PREFECT__FLOW_RUN_ID"] = child_flow_run_id
        child_env["PREFECT__FLOW_ENTRYPOINT"] = (
            "src/discoverex/application/flows/prefect_subflow.py:run_prefect_engine_entry_flow"
        )
        execute_cmd = [str(python_bin), "-m", "prefect.engine"]
        logger.info(
            "engine child flow handoff: child_flow_run_id=%s entrypoint=%s",
            child_flow_run_id,
            child_env["PREFECT__FLOW_ENTRYPOINT"],
        )
    else:
        logger.info("engine child flow handoff skipped: no parent task context")

    logger.info(
        "engine subprocess launch: cmd=%s flow_run_id=%s entrypoint=%s",
        execute_cmd,
        child_env.get("PREFECT__FLOW_RUN_ID", ""),
        child_env.get("PREFECT__FLOW_ENTRYPOINT", ""),
    )

    proc = subprocess.Popen(
        execute_cmd,
        cwd=cwd,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def stream_stdout() -> None:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            stripped = line.rstrip()
            stdout_lines.append(stripped)
            # Log to DEBUG to keep it in the API but hidden from the default INFO UI
            logger.debug(stripped)
        proc.stdout.close()

    def stream_stderr() -> None:
        if proc.stderr is None:
            return
        for line in iter(proc.stderr.readline, ""):
            stripped = line.rstrip()
            stderr_lines.append(stripped)
            # Log to DEBUG to keep diagnostics quiet during success
            logger.debug(f"[diag] {stripped}")
        proc.stderr.close()

    t_out = threading.Thread(target=stream_stdout, daemon=True)
    t_err = threading.Thread(target=stream_stderr, daemon=True)

    t_out.start()
    t_err.start()

    return_code = proc.wait()
    t_out.join()
    t_err.join()

    stdout = "\n".join(stdout_lines)
    stderr = "\n".join(stderr_lines)

    if return_code != 0:
        # LOUD FAILURE: Flush stderr to ERROR level for immediate visibility in the UI
        if stderr.strip():
            logger.error(f"Engine process failed. Captured stderr:\n{stderr.strip()}")
        
        reason = stderr.strip() or stdout.strip() or f"exit_code={return_code}"
        raise RuntimeError(
            "engine subprocess failed"
            f"\n\nexit_code: {return_code}"
            f"\n\nreason: {reason}"
        )
    
    # QUIET SUCCESS: Only a summary is logged at INFO level (handled by flow.py)
    parsed = _parse_payload_from_stdout(stdout)
    return DispatchResult(payload=parsed, stdout=stdout, stderr=stderr)


def _create_child_flow_run(payload: dict[str, Any]) -> str | None:
    flow_run_ctx = FlowRunContext.get()
    task_run_ctx = TaskRunContext.get()
    if flow_run_ctx is None or task_run_ctx is None or task_run_ctx.task_run is None:
        return None

    from discoverex.application.flows.prefect_subflow import (
        run_prefect_engine_entry_flow,
    )

    with get_client(sync_client=True) as client:
        flow_run = client.create_flow_run(
            flow=run_prefect_engine_entry_flow,
            parameters={
                "command": mapped_command(string_value(payload.get("command"))),
                "args": coerce_args(payload.get("args")),
                "config_name": config_name(payload),
                "config_dir": string_value(payload.get("config_dir")) or "conf",
                "overrides": coerce_overrides(payload.get("overrides")),
                "resolved_config": payload.get("resolved_config"),
            },
            state=Pending(),
            parent_task_run_id=task_run_ctx.task_run.id,
        )
    return str(flow_run.id)


def _parse_payload_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("engine subprocess did not emit a JSON payload on stdout")


def apply_result_defaults(
    *,
    parsed: dict[str, Any],
    job_spec: dict[str, Any],
    flow_run_id: str,
    attempt: int,
    outputs_prefix: str,
) -> None:
    parsed.setdefault("job_name", string_value(job_spec.get("job_name")))
    parsed.setdefault("engine", string_value(job_spec.get("engine")))
    parsed.setdefault("run_mode", string_value(job_spec.get("run_mode")))
    parsed.setdefault("flow_run_id", flow_run_id)
    parsed.setdefault("attempt", attempt)
    parsed.setdefault("outputs_prefix", outputs_prefix)
