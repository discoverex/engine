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
    # Physical metadata populated by Phase 1 (MobileSAM)
    z_index: int = 0
    occlusion_ratio: float = 0.0
    z_depth_hop: int = 0
    neighbor_count: int = 0
    euclidean_distances: list[float] = Field(default_factory=list)


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
