from __future__ import annotations

from discoverex.domain.scene import LayerItem, Scene

from .types import BBoxPayload, CandidateLayerPayload, ObjectEntry, ObjectSourceEntry


def candidate_by_region(scene: Scene) -> dict[str, CandidateLayerPayload]:
    candidates = scene.background.metadata.get("inpaint_layer_candidates", [])
    if not isinstance(candidates, list):
        return {}
    indexed: dict[str, CandidateLayerPayload] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        region_id = item.get("region_id")
        if not isinstance(region_id, str):
            continue
        payload: CandidateLayerPayload = {"region_id": region_id}
        for key in (
            "candidate_image_ref",
            "object_image_ref",
            "processed_object_image_ref",
            "processed_object_mask_ref",
            "object_mask_ref",
            "raw_alpha_mask_ref",
            "patch_image_ref",
            "precomposited_image_ref",
            "blend_mask_ref",
            "edge_mask_ref",
            "core_mask_ref",
            "shadow_ref",
            "edge_blend_ref",
            "core_blend_ref",
            "final_polish_ref",
            "variant_manifest_ref",
            "layer_image_ref",
        ):
            value = item.get(key)
            if isinstance(value, str):
                payload[key] = value
        bbox = item.get("bbox")
        if isinstance(bbox, dict):
            try:
                payload["bbox"] = {
                    "x": float(bbox["x"]),
                    "y": float(bbox["y"]),
                    "w": float(bbox["w"]),
                    "h": float(bbox["h"]),
                }
            except (KeyError, TypeError, ValueError):
                pass
        indexed[region_id] = payload
    return indexed


def build_object_entries(
    *,
    scene: Scene,
    candidates: dict[str, CandidateLayerPayload],
) -> list[ObjectEntry]:
    entries: list[ObjectEntry] = []
    numbered_layers = [
        layer
        for layer in sorted(scene.layers.items, key=lambda item: item.order)
        if layer.source_region_id and layer.source_region_id in candidates
    ]
    for object_number, layer in enumerate(numbered_layers, start=1):
        if layer.bbox is None or layer.source_region_id is None:
            continue
        bbox_payload: BBoxPayload = {
            "x": float(layer.bbox.x),
            "y": float(layer.bbox.y),
            "w": float(layer.bbox.w),
            "h": float(layer.bbox.h),
        }
        entries.append(
            {
                "object_number": object_number,
                "layer_id": layer.layer_id,
                "region_id": layer.source_region_id,
                "center": [
                    round(float(layer.bbox.x + (layer.bbox.w / 2.0)), 3),
                    round(float(layer.bbox.y + (layer.bbox.h / 2.0)), 3),
                ],
                "bbox": bbox_payload,
            }
        )
    return entries


def object_entry_by_region(
    entries: list[ObjectEntry],
) -> dict[str, ObjectEntry]:
    return {entry["region_id"]: entry for entry in entries}


def build_object_source_entries(
    *,
    candidates: dict[str, CandidateLayerPayload],
    entries_by_region: dict[str, ObjectEntry],
) -> list[ObjectSourceEntry]:
    entries: list[ObjectSourceEntry] = []
    for region_id, candidate in candidates.items():
        entry: ObjectSourceEntry = {"region_id": region_id}
        object_entry = entries_by_region.get(region_id)
        if object_entry is not None:
            entry["object_number"] = object_entry["object_number"]
            entry["center"] = object_entry["center"]
        for key in (
            "candidate_image_ref",
            "object_image_ref",
            "processed_object_image_ref",
            "processed_object_mask_ref",
            "layer_image_ref",
            "object_mask_ref",
            "raw_alpha_mask_ref",
            "patch_image_ref",
            "precomposited_image_ref",
            "blend_mask_ref",
            "edge_mask_ref",
            "core_mask_ref",
            "shadow_ref",
            "edge_blend_ref",
            "core_blend_ref",
            "final_polish_ref",
            "variant_manifest_ref",
        ):
            value = candidate.get(key)
            if isinstance(value, str):
                entry[key] = value
        entries.append(entry)
    return entries


def lottie_layer_name(*, layer: LayerItem, object_entry: ObjectEntry | None) -> str:
    if layer.source_region_id is not None and object_entry is not None:
        return (
            f"object {object_entry['object_number']} "
            f"center=({object_entry['center'][0]}, {object_entry['center'][1]})"
        )
    return layer.layer_id
