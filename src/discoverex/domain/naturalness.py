from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NaturalnessRegionInput(BaseModel):
    region_id: str
    final_image_ref: str
    selected_bbox: dict[str, float]
    object_image_ref: str | None = None
    object_mask_ref: str | None = None
    patch_image_ref: str | None = None
    precomposited_image_ref: str | None = None
    blend_mask_ref: str | None = None
    placement_score: float | None = None
    variant_manifest_ref: str | None = None
    mask_source: str | None = None


class NaturalnessRegionScore(BaseModel):
    region_id: str
    natural_hidden_score: float
    placement_fit: float
    seam_visibility: float
    saliency_lift: float
    diagnosis_signals: dict[str, Any] = Field(default_factory=dict)


class NaturalnessEvaluation(BaseModel):
    scene_id: str | None = None
    version_id: str | None = None
    overall_score: float = 0.0
    regions: list[NaturalnessRegionScore] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
