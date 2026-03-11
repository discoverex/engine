from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from prefect import flow

from discoverex.application.contracts.execution.schema import (
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
    return JobSpec(
        run_mode="inline",
        engine="discoverex",
        entrypoint=[
            "/bin/sh",
            "-lc",
            "PYTHONPATH=src python -m discoverex.adapters.outbound.execution.launcher",
        ],
        job_name=job_name,
        engine_run=EngineRunSpecV2(
            contract_version="v2",
            command=cast(Any, command),
            config_name=config_name,
            config_dir=config_dir,
            args=args,
            overrides=overrides or [],
            runtime=runtime or JobRuntime(mode="local"),
        ),
    )


def run_engine_job(
    job_spec: JobSpec | dict[str, Any] | str,
    *,
    cwd: Path | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    parsed = _coerce_job_spec(job_spec)
    preparation = prepare_execution(parsed, cwd=cwd)
    _ = (resume_key, checkpoint_dir)
    payload = run_engine_entry(
        command=_mapped_command(parsed),
        args=dict(parsed.engine_run.args),
        config_name=parsed.engine_run.config_name or _default_config_name(parsed),
        config_dir=parsed.engine_run.config_dir or "conf",
        overrides=list(parsed.engine_run.overrides),
    )
    payload.setdefault("job_name", parsed.job_name)
    payload.setdefault("engine", parsed.engine)
    payload.setdefault("run_mode", parsed.run_mode)
    payload["preparation"] = {
        "mode": parsed.engine_run.runtime.mode,
        "working_directory": str(preparation.working_directory),
        "workspace_directory": str(preparation.workspace_directory),
        "uv_cache_directory": str(preparation.uv_cache_directory),
        "actions": list(preparation.actions),
    }
    return payload


@flow(name="run-engine-job", retries=2, retry_delay_seconds=3)
def run_engine_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    return run_engine_job(
        JobSpec.model_validate_json(job_spec_json),
        cwd=Path.cwd(),
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
    )


def _coerce_job_spec(job_spec: JobSpec | dict[str, Any] | str) -> JobSpec:
    if isinstance(job_spec, JobSpec):
        return job_spec
    if isinstance(job_spec, str):
        return JobSpec.model_validate_json(job_spec)
    return JobSpec.model_validate(job_spec)


def _mapped_command(job_spec: JobSpec) -> str:
    command = job_spec.engine_run.command
    return {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _default_config_name(job_spec: JobSpec) -> str:
    return {
        "gen-verify": "gen_verify",
        "verify-only": "verify_only",
        "replay-eval": "replay_eval",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[job_spec.engine_run.command]
