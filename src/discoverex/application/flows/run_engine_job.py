from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter

from discoverex.application.contracts.execution.schema import (
    EngineRunSpec,
    EngineRunSpecV2,
    JobRuntime,
    JobSpec,
)
from discoverex.application.services.execution_preparer import prepare_execution

from .engine_entry import run_engine_entry


def build_inline_job_spec(
    *,
    command: str,
    args: dict[str, Any],
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    job_name: str | None = None,
    runtime: JobRuntime | None = None,
) -> JobSpec:
    engine_run = EngineRunSpecV2(
        contract_version="v2",
        command=cast(Any, command),
        config_name=config_name,
        config_dir=config_dir,
        args=args,
        overrides=overrides or [],
        runtime=runtime or JobRuntime(mode="local"),
    )
    payload = {
        "run_mode": "inline",
        "engine": "discoverex",
        "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
        "job_name": job_name,
        "inputs": engine_run.model_dump(mode="python"),
    }
    return JobSpec.model_validate(payload)


def run_engine_job(
    job_spec: JobSpec | dict[str, Any] | str,
    *,
    cwd: Path | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    parsed = _coerce_job_spec(job_spec)
    engine_inputs = parsed.inputs
    preparation = prepare_execution(parsed, cwd=cwd)
    _ = (resume_key, checkpoint_dir)
    payload = run_engine_entry(
        command=cast(Any, _mapped_command(parsed)),
        args=dict(engine_inputs.args),
        config_name=engine_inputs.config_name or _default_config_name(parsed),
        config_dir=engine_inputs.config_dir or "conf",
        overrides=list(engine_inputs.overrides),
        resolved_config=engine_inputs.resolved_config,
    )
    payload.setdefault("job_name", parsed.job_name)
    payload.setdefault("engine", parsed.engine)
    payload.setdefault("run_mode", parsed.run_mode)
    payload["preparation"] = {
        "mode": engine_inputs.runtime.mode,
        "working_directory": str(preparation.working_directory),
        "workspace_directory": str(preparation.workspace_directory),
        "uv_cache_directory": str(preparation.uv_cache_directory),
        "actions": list(preparation.actions),
    }
    return payload


def _coerce_job_spec(job_spec: JobSpec | dict[str, Any] | str) -> JobSpec:
    if isinstance(job_spec, JobSpec):
        return job_spec
    if isinstance(job_spec, str):
        return _coerce_job_spec(json.loads(job_spec))
    if "inputs" in job_spec:
        return JobSpec.model_validate(job_spec)
    if "engine_run" in job_spec:
        wrapped = dict(job_spec)
        wrapped["inputs"] = wrapped.pop("engine_run")
        return JobSpec.model_validate(wrapped)
    return _inline_job_spec_from_engine_payload(job_spec)


def _inline_job_spec_from_engine_payload(job_spec: dict[str, Any]) -> JobSpec:
    engine_run_payload = {
        "contract_version": job_spec.get("contract_version", "v2"),
        "command": job_spec.get("command"),
        "config_name": job_spec.get("config_name"),
        "config_dir": job_spec.get("config_dir"),
        "resolved_config": job_spec.get("resolved_config"),
        "args": job_spec.get("args", {}),
        "overrides": job_spec.get("overrides", []),
        "runtime": job_spec.get("runtime", {}),
    }
    engine_run = cast(
        EngineRunSpec,
        TypeAdapter(EngineRunSpec).validate_python(engine_run_payload),
    )
    payload = {
        "run_mode": "inline",
        "engine": "discoverex",
        "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
        "job_name": job_spec.get("job_name"),
        "inputs": engine_run.model_dump(mode="python"),
        "env": job_spec.get("env", {}),
        "outputs_prefix": job_spec.get("outputs_prefix"),
    }
    return JobSpec.model_validate(payload)


def _mapped_command(job_spec: JobSpec) -> str:
    engine_inputs = job_spec.inputs
    command = engine_inputs.command
    return {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _default_config_name(job_spec: JobSpec) -> str:
    engine_inputs = job_spec.inputs
    return {
        "gen-verify": "gen_verify",
        "verify-only": "verify_only",
        "replay-eval": "replay_eval",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[engine_inputs.command]
