from __future__ import annotations

from typing import Any, Literal

from discoverex.domain.scene import Scene

FlowCommand = Literal["generate", "verify", "animate"]


def build_scene_payload(
    scene: Scene,
    artifacts_root: str,
    execution_config_path: str | None = None,
) -> dict[str, str]:
    payload = {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scene_json": f"{artifacts_root}/scenes/{scene.meta.scene_id}/{scene.meta.version_id}/scene.json",
    }
    if execution_config_path:
        payload["execution_config"] = execution_config_path
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
