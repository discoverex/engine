from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from discoverex.config import PipelineConfig
from discoverex.config_loader import resolve_pipeline_config

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
    "STORAGE_API_URL",
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
    "PREFECT_API_URL",
    "PREFECT_FLOW_RUN_ID",
    "PREFECT_FLOW_RUN_NAME",
    "PREFECT_DEPLOYMENT_NAME",
)


class TrackingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str = ""


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_bucket: str = ""
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    metadata_db_url: str = ""
    storage_api_url: str = ""


class WorkerHttpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cf_access_client_id: str = ""
    cf_access_client_secret: str = ""
    prefect_api_url: str = ""


class RuntimePathSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_dir: str = ""
    uv_cache_dir: str = ""
    model_cache_dir: str = ""
    hf_home: str = ""


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_name: str
    config_dir: str = "conf"
    overrides: list[str] = Field(default_factory=list)
    source: str = "hydra+env"
    selected_profile: str = ""
    flow_run_id: str = ""
    flow_run_name: str = ""
    deployment_name: str = ""


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline: PipelineConfig
    tracking: TrackingSettings
    storage: StorageSettings
    worker_http: WorkerHttpSettings
    runtime_paths: RuntimePathSettings
    execution: ExecutionSettings

    @classmethod
    def from_pipeline(
        cls,
        *,
        pipeline: PipelineConfig,
        config_name: str,
        config_dir: str,
        overrides: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> "AppSettings":
        env_map = dict(os.environ if env is None else env)
        runtime_env = pipeline.runtime.env.model_copy(
            update={
                "artifact_bucket": str(
                    env_map.get("ARTIFACT_BUCKET", pipeline.runtime.env.artifact_bucket)
                ).strip(),
                "s3_endpoint_url": str(
                    env_map.get("MLFLOW_S3_ENDPOINT_URL", pipeline.runtime.env.s3_endpoint_url)
                ).strip(),
                "aws_access_key_id": str(
                    env_map.get("AWS_ACCESS_KEY_ID", pipeline.runtime.env.aws_access_key_id)
                ).strip(),
                "aws_secret_access_key": str(
                    env_map.get(
                        "AWS_SECRET_ACCESS_KEY", pipeline.runtime.env.aws_secret_access_key
                    )
                ).strip(),
                "metadata_db_url": str(
                    env_map.get("METADATA_DB_URL", pipeline.runtime.env.metadata_db_url)
                ).strip(),
                "tracking_uri": str(
                    env_map.get("MLFLOW_TRACKING_URI", pipeline.runtime.env.tracking_uri)
                ).strip(),
            }
        )
        pipeline = pipeline.model_copy(
            update={
                "runtime": pipeline.runtime.model_copy(
                    update={"env": runtime_env}
                )
            }
        )
        selected_profile = next(
            (
                item.split("=", 1)[1].strip()
                for item in (overrides or [])
                if str(item).strip().startswith("profile=")
            ),
            "",
        )
        return cls(
            pipeline=pipeline,
            tracking=TrackingSettings(uri=runtime_env.tracking_uri),
            storage=StorageSettings(
                artifact_bucket=runtime_env.artifact_bucket,
                s3_endpoint_url=runtime_env.s3_endpoint_url,
                aws_access_key_id=runtime_env.aws_access_key_id,
                aws_secret_access_key=runtime_env.aws_secret_access_key,
                metadata_db_url=runtime_env.metadata_db_url,
                storage_api_url=str(env_map.get("STORAGE_API_URL", "")).strip(),
            ),
            worker_http=WorkerHttpSettings(
                cf_access_client_id=str(env_map.get("CF_ACCESS_CLIENT_ID", "")).strip(),
                cf_access_client_secret=str(
                    env_map.get("CF_ACCESS_CLIENT_SECRET", "")
                ).strip(),
                prefect_api_url=str(env_map.get("PREFECT_API_URL", "")).strip(),
            ),
            runtime_paths=RuntimePathSettings(
                cache_dir=str(env_map.get("CACHE_DIR", "")).strip(),
                uv_cache_dir=str(env_map.get("UV_CACHE_DIR", "")).strip(),
                model_cache_dir=str(env_map.get("MODEL_CACHE_DIR", "")).strip(),
                hf_home=str(env_map.get("HF_HOME", "")).strip(),
            ),
            execution=ExecutionSettings(
                config_name=config_name,
                config_dir=config_dir,
                overrides=list(overrides or []),
                selected_profile=selected_profile,
                flow_run_id=str(env_map.get("PREFECT_FLOW_RUN_ID", "")).strip(),
                flow_run_name=str(env_map.get("PREFECT_FLOW_RUN_NAME", "")).strip(),
                deployment_name=str(env_map.get("PREFECT_DEPLOYMENT_NAME", "")).strip(),
            ),
        )


def build_settings(
    *,
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    resolved_config: object | None = None,
    env: dict[str, str] | None = None,
) -> AppSettings:
    if isinstance(resolved_config, dict) and "pipeline" in resolved_config:
        return AppSettings.model_validate(resolved_config)
    if isinstance(resolved_config, AppSettings):
        return resolved_config
    env_map = dict(os.environ if env is None else env)
    pipeline = resolve_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )
    runtime_env = pipeline.runtime.env.model_copy(
        update={
            "artifact_bucket": str(
                env_map.get("ARTIFACT_BUCKET", pipeline.runtime.env.artifact_bucket)
            ).strip(),
            "s3_endpoint_url": str(
                env_map.get("MLFLOW_S3_ENDPOINT_URL", pipeline.runtime.env.s3_endpoint_url)
            ).strip(),
            "aws_access_key_id": str(
                env_map.get("AWS_ACCESS_KEY_ID", pipeline.runtime.env.aws_access_key_id)
            ).strip(),
            "aws_secret_access_key": str(
                env_map.get(
                    "AWS_SECRET_ACCESS_KEY", pipeline.runtime.env.aws_secret_access_key
                )
            ).strip(),
            "metadata_db_url": str(
                env_map.get("METADATA_DB_URL", pipeline.runtime.env.metadata_db_url)
            ).strip(),
            "tracking_uri": str(
                env_map.get("MLFLOW_TRACKING_URI", pipeline.runtime.env.tracking_uri)
            ).strip(),
        }
    )
    pipeline = pipeline.model_copy(
        update={
            "runtime": pipeline.runtime.model_copy(
                update={"env": runtime_env}
            )
        }
    )
    return AppSettings.from_pipeline(
        pipeline=pipeline,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        env=env_map,
    )


def coerce_settings(value: AppSettings | PipelineConfig | dict[str, Any]) -> AppSettings:
    if isinstance(value, AppSettings):
        return value
    if isinstance(value, PipelineConfig):
        return AppSettings.from_pipeline(
            pipeline=value,
            config_name="resolved",
            config_dir="conf",
            overrides=[],
        )
    if "pipeline" in value:
        return AppSettings.model_validate(value)
    pipeline = PipelineConfig.model_validate(value)
    return AppSettings.from_pipeline(
        pipeline=pipeline,
        config_name="resolved",
        config_dir="conf",
        overrides=[],
    )


def settings_env_snapshot(env: dict[str, str] | None = None) -> dict[str, str]:
    env_map = dict(os.environ if env is None else env)
    return {
        key: value.strip()
        for key in _ENV_KEYS
        if (value := str(env_map.get(key, "")).strip())
    }


def settings_log_payload(settings: AppSettings) -> dict[str, Any]:
    payload = {
        "tracking_uri": settings.tracking.uri,
        "artifact_bucket": settings.storage.artifact_bucket,
        "s3_endpoint_url": settings.storage.s3_endpoint_url,
        "metadata_db_url": settings.storage.metadata_db_url,
        "storage_api_url": settings.storage.storage_api_url,
        "flow_run_id": settings.execution.flow_run_id,
        "flow_run_name": settings.execution.flow_run_name,
        "deployment_name": settings.execution.deployment_name,
        "config_name": settings.execution.config_name,
        "config_dir": settings.execution.config_dir,
        "selected_profile": settings.execution.selected_profile,
        "source": settings.execution.source,
    }
    return _redact(payload)


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
