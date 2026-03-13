from __future__ import annotations

import json
from typing import Any

from infra.prefect.bootstrap import ensure_repo_paths

ensure_repo_paths()

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
from infra.prefect.job_spec import extract_inputs_payload, load_job_spec
from infra.prefect.provision import provision_runtime_dependencies
from infra.prefect.reporting import log_failure_summary, log_start_summary
from infra.prefect.runtime import build_runtime_env, flow_attempt, outputs_prefix, patched_environ


@flow(name="disoverex-engine-flow", retries=0)
def run_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    flow_run_id = flow_run.get_id() or "unknown-flow-run"
    attempt = flow_attempt()
    try:
        job_spec = load_job_spec(job_spec_json)
        payload = extract_inputs_payload(job_spec)
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
            parsed = prefect_dispatch.dispatch_engine_job(payload)
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


__all__ = ["run_job_flow"]


def ensure_repo_root() -> Any:
    from infra.prefect.bootstrap import repo_root

    return repo_root()
