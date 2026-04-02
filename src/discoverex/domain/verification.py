from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    score: float
    pass_: bool = Field(alias="pass")
    signals: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class FinalVerification(BaseModel):
    total_score: float
    pass_: bool = Field(alias="pass")
    failure_reason: str

    model_config = {"populate_by_name": True}


class HiddenObjectMeta(BaseModel):
    """설계안 §4 — hidden_objects 배열의 단위 원소.

    difficulty_signals 9개 키:
        degree_norm, cluster_density_norm, hop_diameter,
        drr_slope_norm, sigma_threshold_norm,
        similar_count_norm, similar_distance_norm,
        color_contrast_norm, edge_strength_norm
    """

    obj_id: str
    human_field: float
    ai_field: float
    D_obj: float
    difficulty_signals: dict[str, float]


class VerificationBundle(BaseModel):
    logical: VerificationResult
    perception: VerificationResult
    final: FinalVerification
    # 설계안 §4 추가
    scene_difficulty: float = 0.0
    hidden_objects: list[HiddenObjectMeta] = Field(default_factory=list)
