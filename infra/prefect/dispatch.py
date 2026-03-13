from __future__ import annotations

from typing import Any

from infra.prefect.job_spec import (
    coerce_args,
    coerce_overrides,
    config_name,
    load_run_engine_entry,
    mapped_command,
    string_value,
)


def dispatch_engine_job(payload: dict[str, Any]) -> dict[str, Any]:
    run_engine_entry = load_run_engine_entry()
    return run_engine_entry(
        command=mapped_command(string_value(payload.get("command"))),
        args=coerce_args(payload.get("args")),
        config_name=config_name(payload),
        config_dir=string_value(payload.get("config_dir")) or "conf",
        overrides=coerce_overrides(payload.get("overrides")),
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
