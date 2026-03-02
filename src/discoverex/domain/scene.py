from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .goal import Goal
from .region import Region
from .verification import VerificationBundle


class SceneStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    FAILED = "failed"


class SceneMeta(BaseModel):
    scene_id: str
    version_id: str
    status: SceneStatus = SceneStatus.CANDIDATE
    pipeline_run_id: str
    model_versions: dict[str, str] = Field(default_factory=dict)
    config_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_version_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class Background(BaseModel):
    asset_ref: str
    width: int
    height: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObjectGroup(BaseModel):
    object_id: str
    region_ids: list[str]
    properties: dict[str, Any] = Field(default_factory=dict)
    type: str | None = None


class Composite(BaseModel):
    final_image_ref: str
    render_meta: dict[str, Any] = Field(default_factory=dict)


class Answer(BaseModel):
    answer_region_ids: list[str]
    uniqueness_intent: Literal[True] = True


class Difficulty(BaseModel):
    estimated_score: float
    source: str
    calibration_version: str | None = None


class Scene(BaseModel):
    meta: SceneMeta
    background: Background
    regions: list[Region]
    objects: list[ObjectGroup] = Field(default_factory=list)
    composite: Composite
    goal: Goal
    answer: Answer
    verification: VerificationBundle
    difficulty: Difficulty

    @model_validator(mode="after")
    def validate_answer_regions(self) -> "Scene":
        region_ids = {region.region_id for region in self.regions}
        missing = [
            region_id
            for region_id in self.answer.answer_region_ids
            if region_id not in region_ids
        ]
        if missing:
            raise ValueError(
                f"answer.answer_region_ids must exist in regions: {missing}"
            )
        return self
