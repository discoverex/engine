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
    object_image_ref: str | Path | None = None
    object_mask_ref: str | Path | None = None
    object_candidate_ref: str | Path | None = None
    prompt: str = ""
    negative_prompt: str = ""
    output_path: str | Path | None = None
    composite_base_ref: str | Path | None = None
    generation_prompt: str = ""
    generation_strength: float = 0.45
    generation_steps: int = 6
    generation_guidance_scale: float = 2.5
    mask_blur: int = 4
    inpaint_only_masked: bool = True
    masked_area_padding: int = 32


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
    output_paths: list[str]
    image_ref: str
    composite_image_ref: str
    artifact_path: str


class InpaintPrediction(TypedDict, total=False):
    region_id: str
    quality_score: float
    model_id: str
    patch_image_ref: str
    candidate_image_ref: str
    object_image_ref: str
    object_mask_ref: str
    composited_image_ref: str
    precomposited_image_ref: str
    blend_mask_ref: str
    edge_mask_ref: str
    core_mask_ref: str
    shadow_ref: str
    edge_blend_ref: str
    core_blend_ref: str
    final_polish_ref: str
    variant_manifest_ref: str
    placement_variant_id: str
    selected_variant_ref: str
    mask_source: str
    inpaint_mode: str
    placement_score: float
    selected_bbox: dict[str, float]
    object_prompt_resolved: str
    object_negative_prompt_resolved: str
    generation_prompt_resolved: str
    object_model_id: str
    object_sampler: str
    object_steps: int
    object_guidance_scale: float
    object_seed: int | None
    alpha_has_signal: bool
    alpha_bbox: list[int]
    alpha_nonzero_ratio: float
    alpha_mean: float


# ---------------------------------------------------------------------------
# Validator pipeline types (Phase 1–4 inter-phase data contracts)
# ---------------------------------------------------------------------------


class PhysicalMetadata(BaseModel):
    """Phase 1 output: MobileSAM segmentation + geometric analysis."""

    regions: list[dict[str, Any]] = Field(default_factory=list)
    z_index_map: dict[str, int] = Field(default_factory=dict)
    z_depth_hop_map: dict[str, int] = Field(default_factory=dict)
    cluster_density_map: dict[str, int] = Field(default_factory=dict)
    euclidean_distance_map: dict[str, list[float]] = Field(default_factory=dict)
    alpha_degree_map: dict[str, int] = Field(default_factory=dict)
    # alpha overlap 그래프 기준 물리적 연결 차수 (논리 판정에서 logical_degree로 사용)


class ColorEdgeMetadata(BaseModel):
    """Phase 2 output: Classical CV color contrast, edge strength, and similarity features."""

    color_contrast_map: dict[str, float] = Field(default_factory=dict)
    # LAB 색차 근사값 — 낮을수록 배경과 구분 어려움
    edge_strength_map: dict[str, float] = Field(default_factory=dict)
    # Sobel magnitude 평균 — 낮을수록 경계 불분명
    obj_color_map: dict[str, list[float]] = Field(default_factory=dict)
    # 객체 LAB 평균값 [L, a, b] — Phase 4 색상 유사도 계산에 재활용
    hu_moments_map: dict[str, list[float]] = Field(default_factory=dict)
    # Hu Moments (7차원) — Phase 4 형상 유사도 계산에 재활용


class LogicalStructure(BaseModel):
    """Phase 3 output: Moondream2 scene graph + NetworkX graph metrics."""

    relations: list[dict[str, Any]] = Field(default_factory=list)
    degree_map: dict[str, int] = Field(default_factory=dict)
    hop_map: dict[str, int] = Field(default_factory=dict)
    diameter: float = 1.0


class VisualVerification(BaseModel):
    """Phase 4 output: YOLO sigma threshold + CLIP similarity decay slope + visual similarity.

    drr_slope = -slope(log(sigma), similarity): larger = faster decay = harder.
    similar_count_map  — 유사 객체 수 (색상+형상 앙상블 ≥ threshold)
    similar_distance_map — 유사 객체 평균 거리 (낮을수록 혼동 어려움)
    object_count_map   — 객체별 탐지 수 (YOLO detection count, Phase 5 집계 가중치)
    """

    sigma_threshold_map: dict[str, float] = Field(default_factory=dict)
    drr_slope_map: dict[str, float] = Field(default_factory=dict)
    similar_count_map: dict[str, int] = Field(default_factory=dict)
    similar_distance_map: dict[str, float] = Field(default_factory=dict)
    object_count_map: dict[str, int] = Field(default_factory=dict)


class ValidatorInput(BaseModel):
    """Aggregated input for Phase 5 pure computation."""

    physical: PhysicalMetadata
    color_edge: ColorEdgeMetadata = Field(default_factory=ColorEdgeMetadata)
    logical: LogicalStructure
    visual: VisualVerification
