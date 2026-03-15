from __future__ import annotations

from typing import Any, Literal, Protocol

FlowCommand = Literal["generate", "verify", "animate"]


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


def build_scene_payload(
    scene: SceneLike,
    artifacts_root: str,
    execution_config_path: str | None = None,
    mlflow_run_id: str | None = None,
) -> dict[str, str]:
    payload = {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scene_json": f"{artifacts_root}/scenes/{scene.meta.scene_id}/{scene.meta.version_id}/scene.json",
    }
    if execution_config_path:
        payload["execution_config"] = execution_config_path
    if mlflow_run_id:
        payload["mlflow_run_id"] = mlflow_run_id
    failure_reason = (scene.verification.final.failure_reason or "").strip()
    if scene.meta.status.value == "failed" and failure_reason:
        payload["failure_reason"] = failure_reason
    return payload


def build_error_payload(
    *,
    command: FlowCommand,
    args: dict[str, Any],
    exc: Exception,
    execution_config_path: str | None = None,
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
        payload["execution_config"] = execution_config_path
    return payload
