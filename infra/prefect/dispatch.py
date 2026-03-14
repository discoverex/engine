from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infra.prefect.job_spec import (
    string_value,
)


@dataclass
class DispatchResult:
    payload: dict[str, Any]
    stdout: str
    stderr: str


def dispatch_engine_job(payload: dict[str, Any], *, cwd: Path, env: dict[str, str]) -> DispatchResult:
    python_bin = cwd / ".venv" / "bin" / "python"
    if not python_bin.exists():
        raise RuntimeError(f"missing bootstrap python: {python_bin}")
    proc = subprocess.run(
        [str(python_bin), "-m", "discoverex.application.flows.launcher_entry"],
        cwd=cwd,
        env={**env, "ORCH_JOB_INPUTS_JSON": json.dumps(payload, ensure_ascii=True)},
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        reason = stderr.strip() or stdout.strip() or f"exit_code={proc.returncode}"
        raise RuntimeError(
            "engine subprocess failed"
            f"\n\nexit_code: {proc.returncode}"
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
