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
    _ = (cwd, env)
    logger = get_run_logger()

    from discoverex.application.flows.engine_entry import (
        run_prefect_engine_entry_flow,
    )

    nested_payload = {
        "command": mapped_command(string_value(payload.get("command"))),
        "args": coerce_args(payload.get("args")),
        "config_name": config_name(payload),
        "config_dir": string_value(payload.get("config_dir")) or "conf",
        "overrides": coerce_overrides(payload.get("overrides")),
        "resolved_config": payload.get("resolved_config"),
    }
    logger.info(
        "engine nested flow handoff: flow=%s command=%s config_name=%s override_count=%d",
        "discoverex-engine-entry-pipeline",
        nested_payload["command"],
        nested_payload["config_name"],
        len(nested_payload["overrides"]),
    )
    result = run_prefect_engine_entry_flow(**nested_payload)
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
