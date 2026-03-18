from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger
from prefect.runtime import flow_run

from infra.prefect.artifacts import (
    FAILED_STATUSES,
    payload_status,
    raise_if_failed_payload,
    summarize_payload,
    upload_worker_artifacts,
    write_local_artifacts,
)
from infra.prefect.job_spec import (
    coerce_args,
    coerce_overrides,
    config_name as resolve_config_name,
    extract_inputs_payload,
    load_job_spec,
    string_value,
)
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


def _coerce_command_for_deployment(
    payload: dict[str, Any],
    *,
    flow_kind: FlowKind | None,
) -> dict[str, Any]:
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
        extract_inputs_payload(job_spec),
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
        gen_payload = {**payload, "command": "generate"}
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

        verify_payload = {**payload, "command": "verify", "args": verify_args}
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
    payload: dict[str, Any],
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> dict[str, Any]:
    """Internal logic shared between flow entrypoints and decomposed sequences."""
    logger = get_run_logger()
    flow_run_id = flow_run.get_id() or "unknown-flow-run"
    attempt = flow_attempt()
    try:
        logger.info("prefect runtime import path: flow_module=%s", __file__)
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
            payload=payload,
            env=env,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
            outputs_prefix=output_prefix,
        )

        with patched_environ(env):
            provision_runtime_dependencies(
                payload=payload,
                cwd=ensure_repo_root(),
                env=env,
                logger=logger,
            )
            parsed = _run_nested_pipeline_flow(
                payload=payload,
                logger=logger,
            )

        _apply_result_defaults(
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
            stdout_text=json.dumps(parsed, ensure_ascii=True),
            stderr_text="",
        )
        parsed.update(
            upload_worker_artifacts(
                flow_run_id=flow_run_id,
                attempt=attempt,
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


def _run_nested_pipeline_flow(*, payload: dict[str, Any], logger: Any) -> dict[str, Any]:
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
    resolved_config_name = resolve_config_name(payload)
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
        return run_generate_flow(
            args=args,
            config=cfg,
            execution_snapshot=execution_snapshot,
            execution_snapshot_path=execution_snapshot_path,
        )
    if command == "verify":
        return run_verify_flow(
            args=args,
            config=cfg,
            execution_snapshot=execution_snapshot,
            execution_snapshot_path=execution_snapshot_path,
        )
    return animate_stub(
        args=args,
        config=cfg,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


def _apply_result_defaults(
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
