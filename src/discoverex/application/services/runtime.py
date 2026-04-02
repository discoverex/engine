from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from discoverex.artifact_paths import scene_json_path
from discoverex.settings import AppSettings


class _StatusLike(Protocol):
    value: str


class _MetaLike(Protocol):
    scene_id: str
    version_id: str
    status: _StatusLike


class _VerificationFinalLike(Protocol):
    failure_reason: str | None


class _VerificationLike(Protocol):
    final: _VerificationFinalLike


class SceneLike(Protocol):
    meta: _MetaLike
    verification: _VerificationLike


FlowCommand = Literal["generate", "verify", "animate"]


def require_resolved_settings(
    execution_snapshot: dict[str, Any] | None,
    *,
    consumer: str,
) -> AppSettings:
    if not execution_snapshot or not isinstance(
        execution_snapshot.get("resolved_settings"), dict
    ):
        raise RuntimeError(f"{consumer} requires resolved_settings in execution snapshot")
    return AppSettings.model_validate(execution_snapshot["resolved_settings"])


def build_scene_payload(
    scene: SceneLike,
    artifacts_root: str,
    execution_config_path: str | Path | None = None,
    mlflow_run_id: str | None = None,
    effective_tracking_uri: str | None = None,
    flow_run_id: str | None = None,
    artifact_prefix: str | None = None,
) -> dict[str, str]:
    payload = {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scene_json": str(
            scene_json_path(
                artifacts_root,
                scene.meta.scene_id,
                scene.meta.version_id,
            )
        ),
    }
    if execution_config_path:
        payload["execution_config"] = str(execution_config_path)
    if mlflow_run_id:
        payload["mlflow_run_id"] = mlflow_run_id
    if effective_tracking_uri:
        payload["effective_tracking_uri"] = effective_tracking_uri
    if flow_run_id:
        payload["flow_run_id"] = flow_run_id
    if artifact_prefix:
        payload["artifact_prefix"] = artifact_prefix
    failure_reason = (scene.verification.final.failure_reason or "").strip()
    if scene.meta.status.value == "failed" and failure_reason:
        payload["failure_reason"] = failure_reason
    return payload


def build_report_payload(
    *,
    report: str | Path,
    settings: AppSettings,
    execution_config_path: str | Path | None = None,
    tracking_run_id: str | None = None,
) -> dict[str, str]:
    payload = {
        "report": str(report),
        "effective_tracking_uri": settings.tracking.uri,
        "flow_run_id": settings.execution.flow_run_id,
    }
    if execution_config_path:
        payload["execution_config"] = str(execution_config_path)
    if tracking_run_id:
        payload["mlflow_run_id"] = str(tracking_run_id)
    return payload


def build_error_payload(
    *,
    command: FlowCommand,
    args: dict[str, Any],
    exc: Exception,
    execution_config_path: str | Path | None = None,
) -> dict[str, Any]:
    reason = str(exc).strip() or exc.__class__.__name__
    payload: dict[str, Any] = {
        "status": "failed",
        "failure_reason": reason,
        "metadata": {
            "command": command,
            "error_type": exc.__class__.__name__,
        },
    }
    if command == "generate":
        payload.update({"scene_id": "", "version_id": "", "scene_json": ""})
    elif command == "verify":
        payload.update(
            {
                "scene_id": "",
                "version_id": "",
                "scene_json": str(args.get("scene_json", "")),
            }
        )
    else:
        payload.update({"report": ""})
    if execution_config_path:
        payload["execution_config"] = str(execution_config_path)
    return payload
