from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, TypedDict, cast
from urllib import error, request
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from discoverex.settings import AppSettings

logger = logging.getLogger("discoverex.mlflow.linkage")


class UploadedArtifactUris(TypedDict, total=False):
    stdout_uri: str
    stderr_uri: str
    result_uri: str
    manifest_uri: str
    engine_manifest_uri: str


class MlflowTagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str


class MlflowTagUpdateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    tags: list[MlflowTagUpdate]


@dataclass(frozen=True)
class MlflowTagLinkageResult:
    status: str
    linked_tags: dict[str, str]
    error: str = ""


def link_uploaded_artifacts(
    *,
    payload: dict[str, Any],
    uploaded_uris: UploadedArtifactUris,
    engine_mlflow_tags: dict[str, str],
    settings: AppSettings | dict[str, Any] | None = None,
) -> MlflowTagLinkageResult:
    run_id = str(payload.get("mlflow_run_id", "")).strip()
    if not run_id:
        return MlflowTagLinkageResult(
            status="skipped_missing_run_id",
            linked_tags={},
        )
    tracking_uri = _tracking_uri_from_settings(settings)
    if not tracking_uri:
        return MlflowTagLinkageResult(
            status="skipped_missing_tracking_uri",
            linked_tags={},
        )
    tags = _build_tag_updates(
        uploaded_uris=uploaded_uris,
        engine_mlflow_tags=engine_mlflow_tags,
    )
    if not tags:
        return MlflowTagLinkageResult(status="skipped_no_tags", linked_tags={})
    batch = MlflowTagUpdateBatch(
        run_id=run_id,
        tags=[
            MlflowTagUpdate(key=key, value=value)
            for key, value in sorted(tags.items())
        ],
    )
    try:
        loaded_settings = _coerce_settings(settings)
        _apply_mlflow_tags(
            tracking_uri=tracking_uri,
            batch=batch,
            settings=loaded_settings,
        )
    except RuntimeError as exc:
        return MlflowTagLinkageResult(
            status=_linkage_failure_status(exc),
            linked_tags={},
            error=str(exc),
        )
    return MlflowTagLinkageResult(status="linked", linked_tags=tags)


def _build_tag_updates(
    *,
    uploaded_uris: UploadedArtifactUris,
    engine_mlflow_tags: dict[str, str],
) -> dict[str, str]:
    tags: dict[str, str] = {}
    for payload_key, tag_key in (
        ("stdout_uri", "artifact_stdout_uri"),
        ("stderr_uri", "artifact_stderr_uri"),
        ("result_uri", "artifact_result_uri"),
        ("manifest_uri", "artifact_manifest_uri"),
        ("engine_manifest_uri", "artifact_engine_manifest_uri"),
    ):
        value = str(uploaded_uris.get(payload_key, "")).strip()
        if value:
            tags[tag_key] = value
    for key, value in engine_mlflow_tags.items():
        tag_key = str(key).strip()
        tag_value = str(value).strip()
        if tag_key and tag_value:
            tags[tag_key] = tag_value
    return tags


def _apply_mlflow_tags(
    *,
    tracking_uri: str,
    batch: MlflowTagUpdateBatch,
    settings: AppSettings | None,
) -> None:
    scheme = urlsplit(tracking_uri).scheme.lower()
    if scheme in {"http", "https"}:
        _apply_remote_mlflow_tags(
            tracking_uri=tracking_uri,
            batch=batch,
            settings=settings,
        )
        return
    _apply_local_mlflow_tags(tracking_uri=tracking_uri, batch=batch)


def _apply_remote_mlflow_tags(
    *,
    tracking_uri: str,
    batch: MlflowTagUpdateBatch,
    settings: AppSettings | None,
) -> None:
    logger.info(
        "mlflow remote linkage start tracking_uri=%s run_id=%s tag_count=%d",
        tracking_uri,
        batch.run_id,
        len(batch.tags),
    )
    for tag in batch.tags:
        payload = {
            "run_id": batch.run_id,
            "key": tag.key,
            "value": tag.value,
        }
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = request.Request(
            f"{tracking_uri.rstrip('/')}/api/2.0/mlflow/runs/set-tag",
            method="POST",
            data=body,
            headers=_mlflow_headers(settings),
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                resp.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "mlflow remote tag update failed "
                f"run_id={batch.run_id} tag={tag.key} status={exc.code} detail={detail}"
            ) from exc


def _apply_local_mlflow_tags(
    *,
    tracking_uri: str,
    batch: MlflowTagUpdateBatch,
) -> None:
    try:
        import mlflow  # type: ignore
        from mlflow.tracking import MlflowClient  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "mlflow dependency is required for local MLflow tag linkage. "
            "Install with `uv sync --extra tracking`."
        ) from exc
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    for tag in batch.tags:
        client.set_tag(batch.run_id, tag.key, tag.value)


def _mlflow_headers(settings: AppSettings | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "discoverex-worker-mlflow-linkage/1.0",
    }
    cf_id = settings.worker_http.cf_access_client_id.strip() if settings else ""
    cf_secret = settings.worker_http.cf_access_client_secret.strip() if settings else ""
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return cast(dict[str, str], headers)


def _tracking_uri_from_settings(settings: AppSettings | dict[str, Any] | None) -> str:
    loaded = _coerce_settings(settings)
    return loaded.tracking.uri.strip() if loaded is not None else ""


def _coerce_settings(settings: AppSettings | dict[str, Any] | None) -> AppSettings | None:
    if settings is None:
        return None
    if isinstance(settings, AppSettings):
        return settings
    return AppSettings.model_validate(settings)


def _linkage_failure_status(exc: RuntimeError) -> str:
    text = str(exc)
    if "RESOURCE_DOES_NOT_EXIST" in text or "not found" in text.lower():
        return "skipped_run_not_found"
    return "skipped_mlflow_error"
