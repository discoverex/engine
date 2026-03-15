from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prefect import get_run_logger

from infra.prefect.job_spec import (
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

    # Inject parent flow run context to link the sub-process flow in Prefect UI
    from prefect.context import FlowRunContext

    child_env = {**env, "ORCH_JOB_INPUTS_JSON": json.dumps(payload, ensure_ascii=True)}
    
    flow_run_ctx = FlowRunContext.get()
    if flow_run_ctx and flow_run_ctx.flow_run:
        child_env["PREFECT_PARENT_FLOW_RUN_ID"] = str(flow_run_ctx.flow_run.id)

    proc = subprocess.Popen(
        [str(python_bin), "-m", "discoverex.application.flows.launcher_entry"],
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
            logger.info(stripped)
        proc.stdout.close()

    def stream_stderr() -> None:
        if proc.stderr is None:
            return
        for line in iter(proc.stderr.readline, ""):
            stripped = line.rstrip()
            stderr_lines.append(stripped)
            logger.error(f"[stderr] {stripped}")
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
        reason = stderr.strip() or stdout.strip() or f"exit_code={return_code}"
        raise RuntimeError(
            "engine subprocess failed"
            f"\n\nexit_code: {return_code}"
            f"\n\nstderr:\n{stderr.strip()}"
            f"\n\nstdout:\n{stdout.strip()}"
            f"\n\nreason: {reason}"
        )
    parsed = _parse_payload_from_stdout(stdout)
    return DispatchResult(payload=parsed, stdout=stdout, stderr=stderr)


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
