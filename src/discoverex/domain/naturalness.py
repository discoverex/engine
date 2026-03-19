from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TypedDict


class SelectedBBox(TypedDict):
    x: float
    y: float
    w: float
    h: float


class NaturalnessSummary(TypedDict):
    region_count: int
    avg_placement_fit: float
    avg_seam_visibility: float
    avg_saliency_lift: float


def default_summary() -> NaturalnessSummary:
    return {
        "region_count": 0,
        "avg_placement_fit": 0.0,
        "avg_seam_visibility": 0.0,
        "avg_saliency_lift": 0.0,
    }


@dataclass(frozen=True)
class NaturalnessRegionInput:
    region_id: str
    final_image_ref: str
    selected_bbox: SelectedBBox
    object_image_ref: str | None = None
    object_mask_ref: str | None = None
    patch_image_ref: str | None = None
    precomposited_image_ref: str | None = None
    blend_mask_ref: str | None = None
    placement_score: float | None = None
    variant_manifest_ref: str | None = None
    mask_source: str | None = None


@dataclass(frozen=True)
class NaturalnessRegionScore:
    region_id: str
    natural_hidden_score: float
    placement_fit: float
    seam_visibility: float
    saliency_lift: float
    diagnosis_signals: dict[str, float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class NaturalnessEvaluation:
    scene_id: str | None = None
    version_id: str | None = None
    overall_score: float = 0.0
    regions: list[NaturalnessRegionScore] = field(default_factory=list)
    summary: NaturalnessSummary = field(default_factory=default_summary)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
