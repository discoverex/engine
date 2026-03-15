from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from infra.prefect.job_spec import string_value
from infra.prefect.runtime import (
    ARTIFACT_DIR_ENV,
    ARTIFACT_MANIFEST_ENV,
    outputs_prefix,
)

FAILED_STATUSES = {"failed", "error"}


def write_local_artifacts(
    *,
    env: dict[str, str],
    parsed: dict[str, Any],
    flow_run_id: str,
    attempt: int,
    job_spec: dict[str, Any],
    stdout_text: str = "",
    stderr_text: str = "",
) -> dict[str, str]:
    artifact_dir = Path(env[ARTIFACT_DIR_ENV]).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    result_path = artifact_dir / "result.json"
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    result_payload = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "engine": string_value(job_spec.get("engine")),
        "run_mode": string_value(job_spec.get("run_mode")),
        "job_name": string_value(job_spec.get("job_name")),
        "outputs_prefix": outputs_prefix(
            job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
        ),
        "payload": parsed,
    }
    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "result": str(result_path),
        "engine_artifact_dir": str(artifact_dir),
        "engine_artifact_manifest": str(Path(env[ARTIFACT_MANIFEST_ENV]).resolve()),
    }


def upload_worker_artifacts(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    require_manifest: bool,
    logger: Any,
) -> dict[str, Any]:
    if not os.getenv("STORAGE_API_URL", "").strip():
        logger.info("storage upload skipped: STORAGE_API_URL not configured")
        return {}
    from discoverex.orchestrator_contract.output_uploads import (
        upload_engine_artifacts,
        upload_outputs,
    )

    uploaded = upload_outputs(
        flow_run_id=flow_run_id,
        attempt=attempt,
        local_paths=local_paths,
    )
    engine_uploaded = upload_engine_artifacts(
        flow_run_id=flow_run_id,
        attempt=attempt,
        local_paths=local_paths,
        require_manifest=require_manifest,
    )
    payload: dict[str, Any] = {
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
    }
    if engine_uploaded.manifest_uri:
        payload["engine_manifest_uri"] = engine_uploaded.manifest_uri
    if engine_uploaded.artifact_uris:
        payload["engine_artifact_uris"] = engine_uploaded.artifact_uris
    return {key: value for key, value in payload.items() if value}


def payload_status(parsed: dict[str, Any]) -> str:
    return string_value(parsed.get("status")).lower() or "completed"


def raise_if_failed_payload(parsed: dict[str, Any]) -> None:
    status = payload_status(parsed)
    if status not in FAILED_STATUSES:
        return
    reason = string_value(parsed.get("failure_reason")) or (
        "engine payload reported failure"
    )
    raise RuntimeError(
        "engine flow returned failed payload"
        f"\n\nreason: {reason}"
        f"\n\npayload: {json.dumps(parsed, ensure_ascii=True, sort_keys=True)}"
    )


def summarize_payload(parsed: dict[str, Any]) -> dict[str, str]:
    keys = (
        "status",
        "job_name",
        "engine",
        "run_mode",
        "scene_id",
        "version_id",
        "scene_json",
        "report",
        "execution_config",
        "stdout_uri",
        "stderr_uri",
        "result_uri",
        "manifest_uri",
        "engine_manifest_uri",
    )
    summary = {
        key: string_value(parsed.get(key))
        for key in keys
        if string_value(parsed.get(key))
    }
    if not summary:
        return {"status": "completed"}
    return summary
