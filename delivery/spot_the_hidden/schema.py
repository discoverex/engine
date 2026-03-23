from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class StorageType(str, Enum):
    LOCAL = "local"
    S3 = "s3"
    MINIO = "minio"


class RegionBBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class BackgroundImage(BaseModel):
    image_id: str
    src: str
    prompt: str = ""
    width: int
    height: int


class AnswerAsset(BaseModel):
    lottie_id: str
    name: str
    src: str
    bbox: RegionBBox
    prompt: str = ""
    order: int


class HintItem(BaseModel):
    key: str
    value: str


class UiFlags(BaseModel):
    show_region_count_hint: bool = True
    allow_multi_click: bool = False


class PlayableScene(BaseModel):
    background_img: BackgroundImage
    answers: list[AnswerAsset] = Field(default_factory=list)
    goal_text: str | None = None
    hints: list[HintItem] = Field(default_factory=list)
    ui_flags: UiFlags = Field(default_factory=UiFlags)


class AnswerRegion(BaseModel):
    region_id: str
    bbox: RegionBBox
    role: str


class AnswerKey(BaseModel):
    answer_region_ids: list[str]
    regions: list[AnswerRegion]


class SceneRef(BaseModel):
    scene_id: str
    version_id: str
    source_scene_json: str


class DeliveryMeta(BaseModel):
    storage: StorageType
    image_mime: str
    image_sha256: str
    image_bytes: int
    status: str
    difficulty_score: float
    created_at: datetime
    model_versions: dict[str, str] = Field(default_factory=dict)


class GameBundle(BaseModel):
    bundle_version: str = "spot_hidden_v3"
    scene_ref: SceneRef
    playable: PlayableScene
    answer_key: AnswerKey
    delivery_meta: DeliveryMeta
