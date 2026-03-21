from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict


class BBoxPayload(TypedDict):
    x: float
    y: float
    w: float
    h: float


class CandidateLayerPayload(TypedDict, total=False):
    region_id: str
    candidate_image_ref: str
    object_image_ref: str
    object_mask_ref: str
    raw_alpha_mask_ref: str
    patch_image_ref: str
    precomposited_image_ref: str
    blend_mask_ref: str
    edge_mask_ref: str
    core_mask_ref: str
    shadow_ref: str
    edge_blend_ref: str
    core_blend_ref: str
    final_polish_ref: str
    variant_manifest_ref: str
    layer_image_ref: str
    bbox: BBoxPayload


class ObjectEntry(TypedDict):
    object_number: int
    layer_id: str
    region_id: str
    center: list[float]
    bbox: BBoxPayload


class ObjectSourceEntry(TypedDict, total=False):
    region_id: str
    object_number: int
    center: list[float]
    candidate_image_ref: str
    object_image_ref: str
    layer_image_ref: str
    object_mask_ref: str
    raw_alpha_mask_ref: str
    patch_image_ref: str
    precomposited_image_ref: str
    blend_mask_ref: str
    edge_mask_ref: str
    core_mask_ref: str
    shadow_ref: str
    edge_blend_ref: str
    core_blend_ref: str
    final_polish_ref: str
    variant_manifest_ref: str


class IntermediateAssetEntry(TypedDict):
    region_id: str
    kind: str
    path: str


@dataclass(frozen=True)
class OutputExportResult:
    manifest_path: Path
    lottie_path: Path
    layer_paths: list[Path]
    source_layer_paths: list[Path]
    intermediate_paths: list[Path]
