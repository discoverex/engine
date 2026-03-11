from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SCRIPT_DIR = Path(__file__).resolve().parent


class RegisterSettings(BaseSettings):
    prefect_api_url: str = ""
    prefect_deployment: str = ""
    prefect_work_pool: str = "local-process"

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
