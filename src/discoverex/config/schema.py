from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HydraComponentConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    target: str = Field(alias="_target_")

    def as_kwargs(self) -> dict[str, Any]:
        return self.model_dump(mode="python", by_alias=True)


class ModelsConfig(BaseModel):
    hidden_region: HydraComponentConfig
    inpaint: HydraComponentConfig
    perception: HydraComponentConfig
    fx: HydraComponentConfig


class AdaptersConfig(BaseModel):
    artifact_store: HydraComponentConfig
    metadata_store: HydraComponentConfig
    tracker: HydraComponentConfig
    scene_io: HydraComponentConfig
    report_writer: HydraComponentConfig


class RuntimeModelConfig(BaseModel):
    device: Literal["cpu", "cuda"] = "cuda"
    dtype: str = "float16"
    precision: Literal["fp16", "fp32"] = "fp16"
    batch_size: int = 1
    seed: int | None = None

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("batch_size must be >= 1")
        return value


class RuntimeEnvConfig(BaseModel):
    artifact_bucket: str = "discoverex-artifacts"
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    metadata_db_url: str = ""
    tracking_uri: str = "sqlite:///mlflow.db"


class RuntimeConfig(BaseModel):
    width: int = 1024
    height: int = 768
    config_version: str = "config-v1"
    artifacts_root: str = "artifacts"
    model_runtime: RuntimeModelConfig = Field(default_factory=RuntimeModelConfig)
    env: RuntimeEnvConfig = Field(default_factory=RuntimeEnvConfig)

    @field_validator("width", "height")
    @classmethod
    def validate_dimensions(cls, value: int) -> int:
        if value < 1:
            raise ValueError("width/height must be >= 1")
        return value


class ThresholdsConfig(BaseModel):
    logical_pass: float = 0.7
    perception_pass: float = 0.7
    final_pass: float = 0.75

    @field_validator("logical_pass", "perception_pass", "final_pass")
    @classmethod
    def validate_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("threshold must be in [0.0, 1.0]")
        return value


class ModelVersionsConfig(BaseModel):
    hidden_region: str = "hidden-region-v0"
    inpaint: str = "inpaint-v0"
    perception: str = "perception-v0"
    fx: str = "fx-v0"


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: ModelsConfig
    adapters: AdaptersConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    model_versions: ModelVersionsConfig = Field(default_factory=ModelVersionsConfig)
