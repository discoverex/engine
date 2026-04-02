from __future__ import annotations

from typing import Any

from discoverex.settings import AppSettings
from discoverex.adapters.outbound.storage.output_uploads import (
    upload_engine_artifacts,
    upload_outputs,
)
from discoverex.adapters.outbound.tracking.linkage import link_uploaded_artifacts


def publish_worker_artifacts(
    *,
    flow_run_id: str,
    attempt: int,
    parsed: dict[str, Any],
    local_paths: dict[str, str],
    require_manifest: bool,
    settings: AppSettings | dict[str, Any] | None,
) -> dict[str, Any]:
    loaded = _coerce_settings(settings)
    if loaded is None or not loaded.storage.storage_api_url.strip():
        return {}
    uploaded = upload_outputs(
        flow_run_id=flow_run_id,
        attempt=attempt,
        local_paths=local_paths,
        settings=loaded,
    )
    engine_uploaded = upload_engine_artifacts(
        flow_run_id=flow_run_id,
        attempt=attempt,
        local_paths=local_paths,
        require_manifest=require_manifest,
        settings=loaded,
    )
    payload: dict[str, Any] = {
        "artifact_bucket": loaded.storage.artifact_bucket,
        "artifact_prefix": _artifact_prefix(flow_run_id=flow_run_id, attempt=attempt),
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
    }
    if engine_uploaded.manifest_uri:
        payload["engine_manifest_uri"] = engine_uploaded.manifest_uri
    if engine_uploaded.artifact_uris:
        payload["engine_artifact_uris"] = engine_uploaded.artifact_uris
    linkage = link_uploaded_artifacts(
        payload=parsed,
        uploaded_uris=payload,
        engine_mlflow_tags=engine_uploaded.mlflow_tags,
        settings=loaded,
    )
    payload["mlflow_linkage_status"] = linkage.status
    if linkage.linked_tags:
        payload["mlflow_linked_tags"] = linkage.linked_tags
    if linkage.error:
        payload["mlflow_linkage_error"] = linkage.error
    return {key: value for key, value in payload.items() if value}


def summarize_engine_payload(parsed: dict[str, Any]) -> dict[str, str]:
    keys = (
        "status",
        "job_name",
        "engine",
        "run_mode",
        "flow_run_id",
        "attempt",
        "scene_id",
        "version_id",
        "scene_json",
        "artifact_bucket",
        "artifact_prefix",
        "report",
        "execution_config",
        "mlflow_run_id",
        "effective_tracking_uri",
        "stdout_uri",
        "stderr_uri",
        "result_uri",
        "manifest_uri",
        "engine_manifest_uri",
        "mlflow_linkage_status",
        "mlflow_linkage_error",
    )
    summary = {
        key: _string_value(parsed.get(key))
        for key in keys
        if _string_value(parsed.get(key))
    }
    if not summary:
        return {"status": "completed"}
    return summary


def _coerce_settings(settings: AppSettings | dict[str, Any] | None) -> AppSettings | None:
    if settings is None:
        return None
    if isinstance(settings, AppSettings):
        return settings
    return AppSettings.model_validate(settings)


def _artifact_prefix(*, flow_run_id: str, attempt: int) -> str:
    return f"jobs/{flow_run_id}/attempt-{attempt}/"


def _string_value(value: object) -> str:
    return str(value or "").strip()
