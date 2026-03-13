from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SCRIPT_DIR = Path(__file__).resolve().parent


class RegisterSettings(BaseSettings):
    prefect_api_url: str = ""
    prefect_deployment: str = "discoverex-engine-job"
    prefect_work_pool: str = "local-process"
    prefect_work_queue: str = "gpu-fixed"
    prefect_colab_deployment: str = "discoverex-engine-job-colab"
    prefect_colab_work_queue: str = "gpu-colab"
    prefect_compat_deployment: str = "engine-job"
    prefect_compat_work_queue: str = "gpu-fixed"
    prefect_compat_colab_deployment: str = "engine-job-colab"
    prefect_compat_colab_work_queue: str = "gpu-colab"
    register_flow_source: str = "/app"
    register_flow_entrypoint: str = "infra/prefect/flow.py:run_job_flow"
    register_flow_ref: str = "dev"
    register_deployment_version: str = ""

    prefect_cf_access_client_id: str = ""
    prefect_cf_access_client_secret: str = ""

    engine_repo_url: str = "https://github.com/discoverex/engine.git"
    engine_repo_ref: str = "dev"
    engine_execution_profile: str = "generator-sdxl-gpu"

    mlflow_tracking_uri: str = ""
    mlflow_s3_endpoint_url: str = ""

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""

    artifact_bucket: str = ""
    metadata_db_url: str = ""

    cf_access_client_id: str = ""
    cf_access_client_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=SCRIPT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


SETTINGS = RegisterSettings()


def default_deployment_version() -> str:
    explicit = SETTINGS.register_deployment_version.strip()
    if explicit:
        return explicit
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
