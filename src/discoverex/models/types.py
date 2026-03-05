from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from pydantic import BaseModel, Field


class ModelRuntimeContext(BaseModel):
    device: str = "cuda"
    dtype: str = "float16"
    batch_size: int = 1
    precision: str = "fp16"
    seed: int | None = None


class ModelHandle(BaseModel):
    name: str
    version: str
    runtime: str
    model_id: str = ""
    revision: str = "main"
    tokenizer_id: str | None = None
    device: str = "cuda"
    dtype: str = "float16"
    extra: dict[str, Any] = Field(default_factory=dict)


class HiddenRegionRequest(BaseModel):
    image_ref: str | Path | None = None
    image_bytes: bytes | None = None
    width: int = 0
    height: int = 0
    thresholds: dict[str, float] = Field(default_factory=dict)


class InpaintRequest(BaseModel):
    image_ref: str | Path | None = None
    region_id: str = ""
    bbox: tuple[float, float, float, float] | None = None
    region_mask_ref: str | Path | None = None
    prompt: str = ""
    negative_prompt: str = ""
    output_path: str | Path | None = None
    composite_base_ref: str | Path | None = None
    generation_prompt: str = ""
    generation_strength: float = 0.45
    generation_steps: int = 6
    generation_guidance_scale: float = 2.5


class PerceptionRequest(BaseModel):
    image_ref: str | Path | None = None
    region_count: int = 0
    regions: list[dict[str, Any]] = Field(default_factory=list)
    question_context: str = ""


class FxRequest(BaseModel):
    image_ref: str | Path | None = None
    mode: str = "default"
    params: dict[str, Any] = Field(default_factory=dict)


class FxPrediction(TypedDict, total=False):
    fx: str
    output_path: str
    image_ref: str
    composite_image_ref: str
    artifact_path: str


class InpaintPrediction(TypedDict, total=False):
    region_id: str
    quality_score: float
    model_id: str
    patch_image_ref: str
    composited_image_ref: str
    inpaint_mode: str


# ---------------------------------------------------------------------------
# Validator pipeline types (Phase 1–4 inter-phase data contracts)
# ---------------------------------------------------------------------------

class PhysicalMetadata(BaseModel):
    """Phase 1 output: MobileSAM segmentation + geometric analysis."""
    regions: list[dict[str, Any]] = Field(default_factory=list)
    occlusion_map: dict[str, float] = Field(default_factory=dict)
    z_index_map: dict[str, int] = Field(default_factory=dict)
    z_depth_hop_map: dict[str, int] = Field(default_factory=dict)
    cluster_density_map: dict[str, int] = Field(default_factory=dict)
    euclidean_distance_map: dict[str, list[float]] = Field(default_factory=dict)


class LogicalStructure(BaseModel):
    """Phase 2 output: Moondream2 scene graph + NetworkX graph metrics."""
    relations: list[dict[str, Any]] = Field(default_factory=list)
    degree_map: dict[str, int] = Field(default_factory=dict)
    hop_map: dict[str, int] = Field(default_factory=dict)
    diameter: float = 1.0


class VisualVerification(BaseModel):
    """Phase 3 output: YOLO sigma threshold + CLIP detail retention rate."""
    sigma_threshold_map: dict[str, float] = Field(default_factory=dict)
    detail_retention_rate_map: dict[str, float] = Field(default_factory=dict)


class ValidatorInput(BaseModel):
    """Aggregated input for Phase 4 pure computation."""
    physical: PhysicalMetadata
    logical: LogicalStructure
    visual: VisualVerification
