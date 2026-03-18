from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prefect import get_run_logger

from infra.prefect.job_spec import (
    config_name,
    coerce_args,
    coerce_overrides,
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
    _ = (cwd, env)
    logger = get_run_logger()

    from discoverex.application.flows.engine_entry import (
        build_execution_snapshot,
        load_pipeline_config,
        normalize_pipeline_config_for_worker_runtime,
        write_execution_snapshot,
    )
    from discoverex.flows.generate import run_generate_flow
    from discoverex.flows.verify import run_verify_flow
    from discoverex.flows.subflows import animate_stub

    command = string_value(payload.get("command"))
    args = coerce_args(payload.get("args"))
    resolved_config = payload.get("resolved_config")
    resolved_config_name = config_name(payload)
    resolved_config_dir = string_value(payload.get("config_dir")) or "conf"
    overrides = coerce_overrides(payload.get("overrides"))

    cfg = load_pipeline_config(
        config_name=resolved_config_name,
        config_dir=resolved_config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )
    cfg = normalize_pipeline_config_for_worker_runtime(cfg)
    execution_snapshot = build_execution_snapshot(
        command=command,
        args=args,
        config_name=resolved_config_name,
        config_dir=resolved_config_dir,
        overrides=overrides,
        config=cfg,
    )
    execution_snapshot_path = write_execution_snapshot(
        artifacts_root=Path(cfg.runtime.artifacts_root).resolve(),
        command=command,
        snapshot=execution_snapshot,
    )

    flow_name = {
        "generate": "discoverex-generate-pipeline",
        "verify": "discoverex-verify-pipeline",
        "animate": "discoverex-animate-pipeline",
    }[command]
    logger.info(
        "engine nested flow handoff: flow=%s command=%s config_name=%s override_count=%d",
        flow_name,
        command,
        resolved_config_name,
        len(overrides),
    )
    if command == "generate":
        result = run_generate_flow(
            args=args,
            config=cfg,
            execution_snapshot=execution_snapshot,
            execution_snapshot_path=execution_snapshot_path,
        )
    elif command == "verify":
        result = run_verify_flow(
            args=args,
            config=cfg,
            execution_snapshot=execution_snapshot,
            execution_snapshot_path=execution_snapshot_path,
        )
    else:
        result = animate_stub(
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
