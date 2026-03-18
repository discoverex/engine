from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from discoverex.config import PipelineConfig

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(secret|token|password|credential|api[_-]?key|access[_-]?key|tracking_uri|db_url)",
    re.IGNORECASE,
)
_ENV_KEYS = (
    "MLFLOW_TRACKING_URI",
    "MLFLOW_S3_ENDPOINT_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "ARTIFACT_BUCKET",
    "METADATA_DB_URL",
    "cf_access_client_id",
    "cf_access_client_secret",
    "PREFECT_FLOW_RUN_ID",
    "PREFECT_FLOW_RUN_NAME",
    "PREFECT_DEPLOYMENT_NAME",
)


def build_execution_snapshot(
    *,
    command: str,
    args: dict[str, Any],
    config_name: str,
    config_dir: str,
    overrides: list[str],
    config: PipelineConfig,
) -> dict[str, Any]:
    env_values = {
        key: value for key in _ENV_KEYS if (value := os.getenv(key, "").strip())
    }
    snapshot = {
        "command": command,
        "config_name": config_name,
        "config_dir": config_dir,
        "args": args,
        "overrides": overrides,
        "resolved_config": config.model_dump(mode="python"),
        "runtime_env": env_values,
    }
    return cast(dict[str, Any], _redact(snapshot))


def redact_for_logging(value: Any) -> Any:
    return _redact(value)


def write_execution_snapshot(
    *,
    artifacts_root: Path,
    command: str,
    snapshot: dict[str, Any],
) -> Path:
    target_dir = artifacts_root / "debug" / "execution" / command / uuid4().hex[:12]
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "resolved_execution_config.json"
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def update_execution_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_tracking_params(snapshot: dict[str, Any] | None) -> dict[str, str]:
    if snapshot is None:
        return {}
    resolved = snapshot.get("resolved_config", {})
    if not isinstance(resolved, dict):
        resolved = {}
    runtime = _as_dict(resolved.get("runtime"))
    model_runtime = _as_dict(runtime.get("model_runtime"))
    adapters = _as_dict(resolved.get("adapters"))
    models = _as_dict(resolved.get("models"))
    params: dict[str, str] = {
        "command": str(snapshot.get("command", "")),
        "config_name": str(snapshot.get("config_name", "")),
        "config_dir": str(snapshot.get("config_dir", "")),
        "runtime.config_version": str(runtime.get("config_version", "")),
        "runtime.model_runtime.device": str(model_runtime.get("device", "")),
        "runtime.model_runtime.precision": str(model_runtime.get("precision", "")),
        "adapters.artifact_store": _target_name(adapters.get("artifact_store")),
        "adapters.tracker": _target_name(adapters.get("tracker")),
    }
    args = snapshot.get("args", {})
    if isinstance(args, dict):
        for key in ("sweep_id", "combo_id", "scenario_id", "search_stage"):
            value = str(args.get(key, "")).strip()
            if value:
                params[f"args.{key}"] = value
    overrides = snapshot.get("overrides", [])
    if isinstance(overrides, list):
        for name, value in _tracking_override_params(overrides).items():
            params[name] = value
    for model_name in (
        "background_generator",
        "hidden_region",
        "inpaint",
        "perception",
        "fx",
    ):
        params[f"models.{model_name}"] = _target_name(models.get(model_name))
    return {key: value for key, value in params.items() if value}


def summarize_for_logging(snapshot: dict[str, Any]) -> dict[str, str]:
    tracking = build_tracking_params(snapshot)
    return {
        "command": tracking.get("command", ""),
        "config_name": tracking.get("config_name", ""),
        "artifact_store": tracking.get("adapters.artifact_store", ""),
        "tracker": tracking.get("adapters.tracker", ""),
        "device": tracking.get("runtime.model_runtime.device", ""),
    }


def _target_name(value: Any) -> str:
    data = _as_dict(value)
    target = str(data.get("_target_", "") or data.get("target", "")).strip()
    if not target:
        return ""
    return target.rsplit(".", 1)[-1]


def _redact(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {name: _redact(item, key=name) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key=key) for item in value]
    if isinstance(value, str) and _is_sensitive_key(key):
        return "***REDACTED***"
    return value


def _is_sensitive_key(key: str) -> bool:
    upper = key.upper()
    return bool(
        key
        and (
            _SENSITIVE_KEY_PATTERN.search(key)
            or upper.startswith("CF_ACCESS_")
            or upper in {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
        )
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tracking_override_params(overrides: list[Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    for raw in overrides:
        text = str(raw).strip()
        if not text or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value or _is_sensitive_key(key):
            continue
        params[f"override.{_sanitize_tracking_key(key)}"] = value
    return params


def _sanitize_tracking_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip("/"))
