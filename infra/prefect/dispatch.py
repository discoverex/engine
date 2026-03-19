from __future__ import annotations

import importlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from prefect import get_run_logger

from infra.prefect.job_spec import (
    coerce_args,
    coerce_overrides,
    config_name,
    string_value,
)


class EnginePayload(TypedDict, total=False):
    command: str
    args: dict[str, Any]
    resolved_config: object
    config_name: str
    config_dir: str
    overrides: list[str]
    some: object


@dataclass
class DispatchResult:
    payload: dict[str, Any]
    stdout: str
    stderr: str


def _worker_python(cwd: Path) -> str:
    candidate = cwd / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return "python3"


def _dispatch_via_subprocess(
    payload: EnginePayload,
    *,
    cwd: Path,
    env: dict[str, str],
) -> DispatchResult:
    proc = subprocess.Popen(  # noqa: S603
        [
            _worker_python(cwd),
            "-m",
            "discoverex.application.flows.run_engine_job",
            json.dumps(payload, ensure_ascii=True),
        ],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    exit_code = proc.wait()
    stdout = proc.stdout.read() if proc.stdout is not None else ""
    stderr = proc.stderr.read() if proc.stderr is not None else ""
    if exit_code != 0:
        reason = next((line.strip() for line in stderr.splitlines() if line.strip()), "")
        raise RuntimeError(
            "engine subprocess failed\n"
            f"exit_code: {exit_code}\n"
            f"reason: {reason}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )
    parsed = json.loads(stdout) if stdout.strip() else {}
    return DispatchResult(payload=parsed, stdout=stdout, stderr=stderr)


def dispatch_engine_job(
    payload: EnginePayload,
    *,
    cwd: Path,
    env: dict[str, str],
) -> DispatchResult:
    logger = get_run_logger()
    engine_entry = cast(
        Any,
        importlib.import_module("discoverex.application.flows.engine_entry"),
    )

    command = string_value(payload.get("command"))
    if not command:
        return _dispatch_via_subprocess(payload, cwd=cwd, env=env)

    args = coerce_args(payload.get("args"))
    resolved_config = payload.get("resolved_config")
    resolved_config_name = config_name(cast(dict[str, Any], payload))
    resolved_config_dir = string_value(payload.get("config_dir")) or "conf"
    overrides = coerce_overrides(payload.get("overrides"))

    cfg = engine_entry.load_pipeline_config(
        config_name=resolved_config_name,
        config_dir=resolved_config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )
    cfg = engine_entry.normalize_pipeline_config_for_worker_runtime(cfg)
    execution_snapshot = engine_entry.build_execution_snapshot(
        command=command,
        args=args,
        config_name=resolved_config_name,
        config_dir=resolved_config_dir,
        overrides=overrides,
        config=cfg,
    )
    execution_snapshot_path = engine_entry.write_execution_snapshot(
        artifacts_root=Path(cfg.runtime.artifacts_root).resolve(),
        command=command,
        snapshot=execution_snapshot,
    )

    subflow = engine_entry._resolve_subflow(
        cfg, cast(Literal["generate", "verify", "animate"], command)
    )
    flow_name = (
        getattr(subflow, "name", "") or getattr(subflow, "__name__", "") or command
    )
    logger.info(
        "engine nested flow handoff: flow=%s command=%s config_name=%s override_count=%d",
        flow_name,
        command,
        resolved_config_name,
        len(overrides),
    )
    result = subflow(
        args=args,
        config=cfg,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    return DispatchResult(
        payload=result,
        stdout=json.dumps(result, ensure_ascii=True),
        stderr="",
    )


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
