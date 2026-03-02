from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GeometryType(str, Enum):
    BBOX = "bbox"


class BBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Geometry(BaseModel):
    type: GeometryType = GeometryType.BBOX
    bbox: BBox
    mask_ref: str | None = None


class RegionRole(str, Enum):
    CANDIDATE = "candidate"
    DISTRACTOR = "distractor"
    ANSWER = "answer"
    OBJECT = "object"


class RegionSource(str, Enum):
    CANDIDATE_MODEL = "candidate_model"
    INPAINT = "inpaint"
    FX = "fx"
    MANUAL = "manual"


class Region(BaseModel):
    region_id: str
    geometry: Geometry
    role: RegionRole
    source: RegionSource
    attributes: dict[str, Any] = Field(default_factory=dict)
    version: int
    linked_object_id: str | None = None
