from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HydraComponentConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    target: str = Field(alias="_target_")

    def as_kwargs(self) -> dict[str, Any]:
        return self.model_dump(mode="python", by_alias=True)


class ModelsConfig(BaseModel):
    background_generator: HydraComponentConfig
    background_upscaler: HydraComponentConfig
    object_generator: HydraComponentConfig
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


class FlowsConfig(BaseModel):
    generate: HydraComponentConfig
    verify: HydraComponentConfig
    animate: HydraComponentConfig


class RegionSelectionConfig(BaseModel):
    strategy: Literal["patch_similarity_v2", "legacy_detr"] = "patch_similarity_v2"
    max_regions: int = 3
    iou_threshold: float = 0.12
    stride_ratio: float = 0.5
    scale_factors: list[float] = Field(default_factory=lambda: [1.0, 1.15])
    enable_fallback_relaxation: bool = True
    fallback_iou_threshold: float = 0.35
    fallback_scale_factors: list[float] = Field(default_factory=lambda: [0.9, 1.0])


class ObjectVariantsConfig(BaseModel):
    default_count: int = 3
    obj_bg_ratio: float = 0.10
    rotation_degrees: list[float] = Field(default_factory=lambda: [-12.0, 0.0, 12.0])
    scale_factors: list[float] = Field(default_factory=lambda: [0.9, 1.0, 1.1])
    max_variants_per_object: int = 8
    canvas_padding: int = 12


class PatchSimilarityConfig(BaseModel):
    lab_weight: float = 0.35
    lbp_weight: float = 0.20
    gabor_weight: float = 0.0
    hog_weight: float = 0.25
    top_k_candidates: int = 14
    lbp_points: int = 16
    lbp_radius: int = 2
    gabor_frequencies: list[float] = Field(default_factory=lambda: [0.12, 0.2])
    gabor_thetas: list[float] = Field(default_factory=lambda: [0.0, 0.78539816339])
    hog_orientations: int = 9
    hog_pixels_per_cell: int = 8
    min_patch_side: int = 48


class ColorHarmonizationConfig(BaseModel):
    enabled: bool = True
    blend_alpha: float = 0.65


class RuntimeModelConfig(BaseModel):
    device: Literal["cpu", "cuda"] = "cuda"
    dtype: str = "float16"
    precision: Literal["fp16", "fp32"] = "fp16"
    batch_size: int = 1
    seed: int | None = None
    offload_mode: Literal["none", "model", "sequential"] = "none"
    enable_attention_slicing: bool = False
    enable_vae_slicing: bool = False
    enable_vae_tiling: bool = False
    enable_xformers_memory_efficient_attention: bool = False
    enable_fp8_layerwise_casting: bool = False
    enable_channels_last: bool = False

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("batch_size must be >= 1")
        return value


class RuntimeEnvConfig(BaseModel):
    artifact_bucket: str = "discoverex-artifacts"
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    metadata_db_url: str = ""
    tracking_uri: str = ""


class RuntimeConfig(BaseModel):
    width: int = 1024
    height: int = 768
    background_upscale_factor: int = 1
    background_upscale_mode: Literal["hires", "realesrgan", "none"] = "none"
    config_version: str = "config-v1"
    artifacts_root: str = "artifacts"
    model_runtime: RuntimeModelConfig = Field(default_factory=RuntimeModelConfig)
    env: RuntimeEnvConfig = Field(default_factory=RuntimeEnvConfig)

    @model_validator(mode="before")
    @classmethod
    def normalize_background_upscale_mode(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "background_upscale_mode" in value:
            return value
        legacy = value.get("background_hires_mode")
        mapping = {
            "detail_reconstruct": "hires",
            "canvas_then_detail": "hires",
            "canvas_only": "realesrgan",
            "none": "none",
        }
        if isinstance(legacy, str) and legacy.strip():
            value = dict(value)
            value["background_upscale_mode"] = mapping.get(
                legacy.strip(), legacy.strip()
            )
        return value

    @field_validator("width", "height", "background_upscale_factor")
    @classmethod
    def validate_dimensions(cls, value: int) -> int:
        if value < 1:
            raise ValueError("width/height/background_upscale_factor must be >= 1")
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
    background_generator: str = "background-generator-v0"
    background_upscaler: str = "background-upscaler-v0"
    object_generator: str = "object-generator-v0"
    hidden_region: str = "hidden-region-v0"
    inpaint: str = "inpaint-v0"
    perception: str = "perception-v0"
    fx: str = "fx-v0"


class ValidatorModelsConfig(BaseModel):
    physical_extraction: HydraComponentConfig
    logical_extraction: HydraComponentConfig
    visual_verification: HydraComponentConfig


class ValidatorThresholdsConfig(BaseModel):
    difficulty_min: float = 0.1  # 설계안 §3 MVP 변수
    difficulty_max: float = 0.9  # 설계안 §3 MVP 변수
    hidden_obj_min: int = 3  # 설계안 §3 — is_hidden() 통과 객체 수 기준

    @field_validator("difficulty_min", "difficulty_max")
    @classmethod
    def validate_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("value must be in [0.0, 1.0]")
        return value


class ValidatorWeightsConfig(BaseModel):
    """ScoringWeights 의 config 레이어 쌍.

    YAML weights: 섹션 값을 파싱하며, 미지정 필드는 코드 기본값을 사용한다.
    factory.py 에서 ScoringWeights(**cfg.weights.model_dump()) 로 변환된다.
    """

    # integrate_verification_v2 — perception sub-score
    perception_sigma: float = Field(0.50, ge=0.0)
    perception_drr: float = Field(0.50, ge=0.0)
    # integrate_verification_v2 — logical sub-score
    logical_hop: float = Field(0.55, ge=0.0)
    logical_degree: float = Field(0.45, ge=0.0)
    # integrate_verification_v2 — total 집계
    total_perception: float = Field(0.45, ge=0.0)
    total_logical: float = Field(0.55, ge=0.0)
    # compute_difficulty D(obj) 항별 가중치 (합계 = 1.00)
    difficulty_degree: float = Field(0.14, ge=0.0)
    difficulty_cluster: float = Field(0.12, ge=0.0)
    difficulty_hop: float = Field(0.14, ge=0.0)
    difficulty_drr: float = Field(0.14, ge=0.0)
    difficulty_sigma: float = Field(0.12, ge=0.0)
    difficulty_similar_count: float = Field(0.11, ge=0.0)
    difficulty_similar_dist: float = Field(0.09, ge=0.0)
    difficulty_color_contrast: float = Field(0.07, ge=0.0)
    difficulty_edge_strength: float = Field(0.07, ge=0.0)


class ValidatorPipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: ValidatorModelsConfig
    adapters: AdaptersConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    thresholds: ValidatorThresholdsConfig = Field(
        default_factory=ValidatorThresholdsConfig
    )
    weights: ValidatorWeightsConfig = Field(default_factory=ValidatorWeightsConfig)
    weights_path: str | None = None  # 지정 시 JSON 파일에서 로드 → weights 필드 무시
    bundle_store_dir: str | None = (
        None  # VerificationBundle 저장 디렉터리 (null 이면 미저장)
    )
    model_versions: ModelVersionsConfig = Field(default_factory=ModelVersionsConfig)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    models: ModelsConfig
    adapters: AdaptersConfig
    flows: FlowsConfig | None = None
    region_selection: RegionSelectionConfig = Field(default_factory=RegionSelectionConfig)
    object_variants: ObjectVariantsConfig = Field(default_factory=ObjectVariantsConfig)
    patch_similarity: PatchSimilarityConfig = Field(
        default_factory=PatchSimilarityConfig
    )
    color_harmonization: ColorHarmonizationConfig = Field(
        default_factory=ColorHarmonizationConfig
    )
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    model_versions: ModelVersionsConfig = Field(default_factory=ModelVersionsConfig)
