from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RunIds(BaseModel):
    model_config = ConfigDict(frozen=True)

    scene_id: str
    version_id: str
    pipeline_run_id: str


class CompositeResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_ref: str
    artifact_path: Path | None


class PromptStageRecord(BaseModel):
    mode: str
    prompt: str = ""
    negative_prompt: str = ""
    source_ref: str | None = None
    output_ref: str | None = None
    used_fallback: bool = False


class RegionPromptRecord(BaseModel):
    region_id: str
    prompt: str = ""
    negative_prompt: str = ""
    generation_prompt: str = ""
    bbox: tuple[float, float, float, float]
    candidate_image_ref: str | None = None
    patch_image_ref: str | None = None
    object_image_ref: str | None = None
    object_mask_ref: str | None = None
    blend_mask_ref: str | None = None
    composited_image_ref: str | None = None


class PromptBundle(BaseModel):
    input_mode: str
    background: PromptStageRecord
    object: PromptStageRecord
    final_fx: PromptStageRecord
    regions: list[RegionPromptRecord] = Field(default_factory=list)
