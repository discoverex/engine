from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, cast

from prefect import flow, get_run_logger
from prefect.runtime import flow_run

from infra.prefect import dispatch as prefect_dispatch
from infra.prefect.artifacts import (
    FAILED_STATUSES,
    payload_status,
    raise_if_failed_payload,
    summarize_payload,
    upload_worker_artifacts,
    write_local_artifacts,
)
from infra.prefect.dispatch import EnginePayload
from infra.prefect.job_spec import extract_inputs_payload, load_job_spec
from infra.prefect.preflight import validate_runtime_services
from infra.prefect.provision import provision_runtime_dependencies
from infra.prefect.reporting import log_failure_summary, log_start_summary
from infra.prefect.runtime import (
    build_runtime_env,
    flow_attempt,
    outputs_prefix,
    patched_environ,
)

FlowKind = str
_FLOW_KIND_BY_COMMAND: dict[str, FlowKind] = {
    "gen-verify": "generate",
    "verify-only": "verify",
    "replay-eval": "animate",
    "generate": "generate",
    "verify": "verify",
    "animate": "animate",
}


def engine_job_task(
    payload: EnginePayload, cwd: Path, env: dict[str, str]
) -> prefect_dispatch.DispatchResult:
    return prefect_dispatch.dispatch_engine_job(payload, cwd=cwd, env=env)


def _coerce_command_for_deployment(
    payload: EnginePayload,
    *,
    flow_kind: FlowKind | None,
) -> EnginePayload:
    if flow_kind is None or flow_kind == "combined":
        return payload
    command = str(payload.get("command", "")).strip()
    if not command:
        payload["command"] = flow_kind
        return payload
    resolved = _FLOW_KIND_BY_COMMAND.get(command)
    if resolved != flow_kind:
        raise RuntimeError(
            f"deployment flow_kind={flow_kind} cannot execute command={command}"
        )
    return payload


def _run_job_flow(
    *,
    job_spec_json: str,
    resume_key: str | None,
    checkpoint_dir: str | None,
    flow_kind: FlowKind | None,
) -> dict[str, Any]:
    job_spec = load_job_spec(job_spec_json)
    payload = _coerce_command_for_deployment(
        cast(EnginePayload, extract_inputs_payload(job_spec)),
        flow_kind=flow_kind,
    )
    return _run_job_flow_logic(
        job_spec_json=job_spec_json,
        payload=payload,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
    )


@flow(name="discoverex-engine-flow", retries=0)
def run_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    return _run_job_flow(
        job_spec_json=job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
        flow_kind=None,
    )


@flow(name="discoverex-generate-flow", retries=0)
def run_generate_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    return _run_job_flow(
        job_spec_json=job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
        flow_kind="generate",
    )


@flow(name="discoverex-verify-flow", retries=0)
def run_verify_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    return _run_job_flow(
        job_spec_json=job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
        flow_kind="verify",
    )


@flow(name="discoverex-animate-flow", retries=0)
def run_animate_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    return _run_job_flow(
        job_spec_json=job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
        flow_kind="animate",
    )


@flow(name="discoverex-combined-flow", retries=0)
def run_combined_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    job_spec = load_job_spec(job_spec_json)
    payload = extract_inputs_payload(job_spec)
    command = str(payload.get("command", "")).strip()

    # If it's a standard composite command, we can decompose it into explicit tasks here.
    # This fulfills the "flows must be explicit" requirement.
    if command == "gen-verify":
        logger.info("executing explicit gen-verify sequence")
        # 1. Generate
        gen_payload = cast(EnginePayload, {**payload, "command": "generate"})
        gen_output = _run_job_flow_logic(
            job_spec_json=job_spec_json,
            payload=gen_payload,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
        )

        # 2. Verify
        # Propagate the scene artifact to the verify stage if needed
        scene_json = gen_output.get("scene_json")
        verify_args = {**payload.get("args", {})}
        if scene_json:
            verify_args["scene_json"] = scene_json

        verify_payload = cast(
            EnginePayload,
            {**payload, "command": "verify", "args": verify_args},
        )
        verify_output = _run_job_flow_logic(
            job_spec_json=job_spec_json,
            payload=verify_payload,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
        )

        # Combine results
        combined = {**gen_output, **verify_output}
        combined["status"] = (
            "completed"
            if gen_output.get("status") == "completed"
            and verify_output.get("status") == "completed"
            else "failed"
        )
        return combined

    # Fallback for other combined commands or simple composition
    return _run_job_flow(
        job_spec_json=job_spec_json,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
        flow_kind="combined",
    )


def _run_job_flow_logic(
    *,
    job_spec_json: str,
    payload: EnginePayload,
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> dict[str, Any]:
    """Internal logic shared between flow entrypoints and decomposed sequences."""
    logger = get_run_logger()
    flow_run_id = flow_run.get_id() or "unknown-flow-run"
    attempt = flow_attempt()
    try:
        logger.info(
            "prefect runtime import path: flow_module=%s dispatch_module=%s dispatch_source=%s",
            __file__,
            inspect.getsourcefile(prefect_dispatch),
            inspect.getsourcefile(prefect_dispatch.dispatch_engine_job),
        )
        job_spec = load_job_spec(job_spec_json)

        output_prefix = outputs_prefix(
            job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
        )
        env = build_runtime_env(
            job_spec=job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
            outputs_prefix=output_prefix,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
        )

        log_start_summary(
            logger=logger,
            job_spec=job_spec,
            payload=cast(dict[str, Any], payload),
            env=env,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
            outputs_prefix=output_prefix,
        )
        validate_runtime_services(
            payload=cast(dict[str, Any], payload),
            env=env,
            logger=logger,
        )

        with patched_environ(env):
            provision_runtime_dependencies(
                payload=cast(dict[str, Any], payload),
                cwd=ensure_repo_root(),
                env=env,
                logger=logger,
            )
            dispatch_result = engine_job_task(
                payload,
                cwd=ensure_repo_root(),
                env=env,
            )
            parsed = dispatch_result.payload

        prefect_dispatch.apply_result_defaults(
            parsed=parsed,
            job_spec=job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
            outputs_prefix=output_prefix,
        )
        local_paths = write_local_artifacts(
            env=env,
            parsed=parsed,
            flow_run_id=flow_run_id,
            attempt=attempt,
            job_spec=job_spec,
            stdout_text=dispatch_result.stdout,
            stderr_text=dispatch_result.stderr,
        )
        parsed.update(
            upload_worker_artifacts(
                flow_run_id=flow_run_id,
                attempt=attempt,
                parsed=parsed,
                local_paths=local_paths,
                require_manifest=payload_status(parsed) not in FAILED_STATUSES,
                logger=logger,
            )
        )
        raise_if_failed_payload(parsed)
        logger.info(
            "engine payload summary: %s",
            json.dumps(summarize_payload(parsed), ensure_ascii=True, sort_keys=True),
        )
        return parsed
    except Exception:
        log_failure_summary(
            logger=logger,
            flow_run_id=flow_run_id,
            attempt=attempt,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
        )
        raise


__all__ = [
    "run_job_flow",
    "run_generate_job_flow",
    "run_verify_job_flow",
    "run_animate_job_flow",
    "run_combined_job_flow",
]


def ensure_repo_root() -> Any:
    from infra.prefect.bootstrap import repo_root

    return repo_root()
