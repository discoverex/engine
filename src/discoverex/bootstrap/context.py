from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from discoverex.config import ModelVersionsConfig, RuntimeConfig, ThresholdsConfig


class AppContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    background_generator_model: Any
    background_upscaler_model: Any
    object_generator_model: Any
    hidden_region_model: Any
    inpaint_model: Any
    perception_model: Any
    fx_model: Any
    artifact_store: Any
    metadata_store: Any
    tracker: Any
    scene_io: Any
    report_writer: Any
    artifacts_root: Path
    runtime: RuntimeConfig
    thresholds: ThresholdsConfig
    model_versions: ModelVersionsConfig
    execution_snapshot: dict[str, object] | None = None
    execution_snapshot_path: Path | None = None
    tracking_run_id: str | None = None
