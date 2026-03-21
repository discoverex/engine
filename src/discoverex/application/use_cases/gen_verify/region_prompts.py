from __future__ import annotations

from discoverex.domain.region import Region
from discoverex.domain.scene import Background
from discoverex.models.types import InpaintPrediction

from .types import RegionPromptRecord


def bbox_payload(region: Region) -> dict[str, float]:
    bbox = region.geometry.bbox
    return {
        "x": bbox.x,
        "y": bbox.y,
        "w": bbox.w,
        "h": bbox.h,
    }


def bbox_tuple(region: Region) -> tuple[float, float, float, float]:
    bbox = region.geometry.bbox
    return (bbox.x, bbox.y, bbox.w, bbox.h)


def record_layer_candidate(
    *,
    background: Background,
    region: Region,
    candidate_ref: object,
    object_ref: object,
    object_mask_ref: object,
    patch_ref: object,
    raw_alpha_mask_ref: object | None = None,
    details: InpaintPrediction | None = None,
) -> None:
    layer_ref = object_ref if isinstance(object_ref, str) and object_ref else patch_ref
    if not isinstance(layer_ref, str) or not layer_ref:
        return
    candidates = background.metadata.setdefault("inpaint_layer_candidates", [])
    if not isinstance(candidates, list):
        return
    payload = {
        "region_id": region.region_id,
        "candidate_image_ref": candidate_ref,
        "object_image_ref": object_ref,
        "object_mask_ref": object_mask_ref,
        "patch_image_ref": patch_ref,
        "layer_image_ref": layer_ref,
        "bbox": bbox_payload(region),
    }
    if isinstance(raw_alpha_mask_ref, str) and raw_alpha_mask_ref:
        payload["raw_alpha_mask_ref"] = raw_alpha_mask_ref
    if details is not None:
        for key in (
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
            value = details.get(key)
            if isinstance(value, str) and value:
                payload[key] = value
    candidates.append(payload)


def build_prompt_record(
    *,
    region: Region,
    object_prompt: str,
    object_negative_prompt: str,
    generation_prompt: str,
    details: InpaintPrediction,
) -> RegionPromptRecord:
    return RegionPromptRecord(
        region_id=region.region_id,
        prompt=object_prompt,
        negative_prompt=object_negative_prompt,
        generation_prompt=generation_prompt,
        bbox=bbox_tuple(region),
        candidate_image_ref=details.get("candidate_image_ref"),
        patch_image_ref=details.get("patch_image_ref"),
        object_image_ref=details.get("object_image_ref"),
        object_mask_ref=details.get("object_mask_ref"),
        blend_mask_ref=details.get("blend_mask_ref"),
        composited_image_ref=details.get("composited_image_ref"),
    )
