from __future__ import annotations

from discoverex.domain.region import Region
from discoverex.domain.scene import Background
from discoverex.models.types import InpaintPrediction
from .objects.types import GeneratedObjectAsset

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


def _candidate_list(background: Background) -> list[dict[str, object]] | None:
    candidates = background.metadata.setdefault("inpaint_layer_candidates", [])
    return candidates if isinstance(candidates, list) else None


def _upsert_candidate(
    *,
    background: Background,
    region_id: str,
    payload: dict[str, object],
) -> None:
    candidates = _candidate_list(background)
    if candidates is None:
        return
    for index, item in enumerate(candidates):
        if isinstance(item, dict) and item.get("region_id") == region_id:
            candidates[index] = {**item, **payload}
            return
    candidates.append(payload)


def record_generated_object_candidate(
    *,
    background: Background,
    region: Region,
    asset: GeneratedObjectAsset,
) -> None:
    payload: dict[str, object] = {
        "region_id": region.region_id,
        "bbox": bbox_payload(region),
        "candidate_image_ref": asset.candidate_ref,
        "generated_object_image_ref": asset.object_ref,
        "generated_object_mask_ref": asset.object_mask_ref,
        "object_prompt_resolved": asset.object_prompt,
        "object_negative_prompt_resolved": asset.object_negative_prompt,
        "object_model_id": asset.object_model_id,
        "object_sampler": asset.object_sampler,
        "object_steps": asset.object_steps,
        "object_guidance_scale": asset.object_guidance_scale,
        "object_seed": asset.object_seed,
        "mask_source": asset.mask_source,
    }
    if asset.raw_alpha_mask_ref:
        payload["generated_raw_alpha_mask_ref"] = asset.raw_alpha_mask_ref
        payload["raw_alpha_mask_ref"] = asset.raw_alpha_mask_ref
    _upsert_candidate(background=background, region_id=region.region_id, payload=payload)


def record_layer_candidate(
    *,
    background: Background,
    region: Region,
    candidate_ref: object,
    object_ref: object,
    object_mask_ref: object,
    patch_ref: object,
    raw_alpha_mask_ref: object | None = None,
    processed_object_ref: object | None = None,
    processed_object_mask_ref: object | None = None,
    details: InpaintPrediction | None = None,
) -> None:
    layer_ref = (
        processed_object_ref
        if isinstance(processed_object_ref, str) and processed_object_ref
        else object_ref if isinstance(object_ref, str) and object_ref else patch_ref
    )
    if not isinstance(layer_ref, str) or not layer_ref:
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
    if isinstance(processed_object_ref, str) and processed_object_ref:
        payload["processed_object_image_ref"] = processed_object_ref
    if isinstance(processed_object_mask_ref, str) and processed_object_mask_ref:
        payload["processed_object_mask_ref"] = processed_object_mask_ref
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
            "selected_variant_ref",
            "object_prompt_resolved",
            "object_negative_prompt_resolved",
            "generation_prompt_resolved",
            "object_model_id",
            "object_sampler",
            "object_steps",
            "object_guidance_scale",
            "object_seed",
            "mask_source",
            "alpha_has_signal",
            "alpha_bbox",
            "alpha_nonzero_ratio",
            "alpha_mean",
        ):
            value = details.get(key)
            if isinstance(value, str) and value:
                payload[key] = value
            elif value is not None:
                payload[key] = value
    _upsert_candidate(background=background, region_id=region.region_id, payload=payload)


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
        object_prompt_resolved=details.get("object_prompt_resolved"),
        object_negative_prompt_resolved=details.get(
            "object_negative_prompt_resolved"
        ),
        generation_prompt_resolved=details.get("generation_prompt_resolved"),
        object_model_id=details.get("object_model_id"),
        object_sampler=details.get("object_sampler"),
        object_steps=details.get("object_steps"),
        object_guidance_scale=details.get("object_guidance_scale"),
        object_seed=details.get("object_seed"),
        selected_variant_ref=details.get("selected_variant_ref"),
        mask_source=details.get("mask_source"),
        alpha_nonzero_ratio=details.get("alpha_nonzero_ratio"),
    )
