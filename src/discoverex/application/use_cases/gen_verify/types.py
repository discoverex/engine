from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class RunIds(BaseModel):
    model_config = ConfigDict(frozen=True)

    scene_id: str
    version_id: str
    pipeline_run_id: str


class CompositeResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_ref: str
    artifact_path: Path | None
