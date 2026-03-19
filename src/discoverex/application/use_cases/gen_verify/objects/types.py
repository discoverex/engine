from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratedObjectAsset:
    region_id: str
    candidate_ref: str
    object_ref: str
    object_mask_ref: str
    width: int
    height: int
    raw_alpha_mask_ref: str | None = None
    mask_source: str = "unknown"
    tight_bbox: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class PlacementAssets:
    object_path: Path
    mask_path: Path
    raw_alpha_path: Path
    width: int
    height: int
    tight_bbox: tuple[int, int, int, int] | None = None
