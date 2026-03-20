from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SCRIPT_DIR = Path(__file__).resolve().parent


class RegisterSettings(BaseSettings):
    engine_name: str = "discoverex"
    prefect_api_url: str = ""
    prefect_deployment_prefix: str = "discoverex-engine"
    prefect_project_name: str = "discoverex-engine"
    prefect_work_pool: str = "discoverex-fixed"
    prefect_work_queue: str = "gpu-fixed"
    prefect_work_image: str = "discoverex-worker:local"
    register_flow_entrypoint: str = "prefect_flow.py:run_combined_job_flow"
    register_flow_ref: str = "dev"
    register_deployment_version: str = ""

    prefect_cf_access_client_id: str = ""
    prefect_cf_access_client_secret: str = ""

    engine_repo_url: str = "https://github.com/discoverex/engine.git"
    engine_repo_ref: str = "dev"
    engine_execution_profile: str = "generator-pixart-gpu"

    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
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
