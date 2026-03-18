"""Animate pipeline configuration schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .schema import HydraComponentConfig, RuntimeConfig


class AnimateModelsConfig(BaseModel):
    mode_classifier: HydraComponentConfig
    vision_analyzer: HydraComponentConfig
    animation_generation: HydraComponentConfig
    ai_validator: HydraComponentConfig
    post_motion_classifier: HydraComponentConfig


class AnimateAdaptersConfig(BaseModel):
    bg_remover: HydraComponentConfig
    numerical_validator: HydraComponentConfig
    mask_generator: HydraComponentConfig
    keyframe_generator: HydraComponentConfig
    format_converter: HydraComponentConfig


class AnimateThresholdsConfig(BaseModel):
    min_motion: float = 0.003
    max_motion: float = 0.15
    max_repeat_peaks: int = 12
    max_edge_ratio: float = 0.08
    max_return_diff: float = 0.40
    max_center_drift: float = 0.12


class AnimatePipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: AnimateModelsConfig
    animate_adapters: AnimateAdaptersConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    thresholds: AnimateThresholdsConfig = Field(
        default_factory=AnimateThresholdsConfig
    )
    max_retries: int = 7
