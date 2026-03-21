from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from discoverex.application.services.artifact_io import (
    publish_worker_artifacts,
    summarize_engine_payload,
)
from discoverex.settings import AppSettings
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
    parsed: dict[str, Any],
    local_paths: dict[str, str],
    require_manifest: bool,
    logger: Any,
) -> dict[str, Any]:
    settings = _settings_from_payload(parsed)
    if settings is None or not settings.storage.storage_api_url.strip():
        logger.info("storage upload skipped: STORAGE_API_URL not configured")
        return {}
    return publish_worker_artifacts(
        flow_run_id=flow_run_id,
        attempt=attempt,
        parsed=parsed,
        local_paths=local_paths,
        require_manifest=require_manifest,
        settings=settings,
    )


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
    return summarize_engine_payload(parsed)


def _settings_from_payload(parsed: dict[str, Any]) -> AppSettings | dict[str, Any] | None:
    execution_config = string_value(parsed.get("execution_config"))
    if not execution_config:
        return None
    path = Path(execution_config)
    if not path.exists():
        return None
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    resolved = snapshot.get("resolved_settings")
    if not isinstance(resolved, dict):
        return None
    try:
        return AppSettings.model_validate(resolved)
    except Exception:
        return None
