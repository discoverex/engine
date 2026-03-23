from __future__ import annotations

from pathlib import Path

from discoverex.domain.scene import Scene

from .types import BBoxPayload, CandidateLayerPayload, ObjectRenderSpec


def compose_display_name(*, prompt: str = "", negative_prompt: str = "") -> str:
    parts = [part.strip() for part in (prompt, negative_prompt) if part and part.strip()]
    return " | ".join(parts)


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
            "raw_generated_image_ref",
            "sam_object_image_ref",
            "sam_object_mask_ref",
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
            "selected_variant_ref",
            "patch_selection_coarse_ref",
            "patch_selection_fine_ref",
            "layer_image_ref",
            "object_prompt_resolved",
            "object_negative_prompt_resolved",
            "generation_prompt_resolved",
            "object_model_id",
            "object_sampler",
            "mask_source",
        ):
            value = item.get(key)
            if isinstance(value, str):
                payload[key] = value
        for key in (
            "object_steps",
            "object_seed",
        ):
            value = item.get(key)
            if isinstance(value, int):
                payload[key] = value
        for key in (
            "object_guidance_scale",
            "alpha_nonzero_ratio",
            "alpha_mean",
        ):
            value = item.get(key)
            if isinstance(value, (int, float)):
                payload[key] = float(value)
        if isinstance(item.get("alpha_has_signal"), bool):
            payload["alpha_has_signal"] = item["alpha_has_signal"]
        if isinstance(item.get("alpha_bbox"), list):
            payload["alpha_bbox"] = item["alpha_bbox"]
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


def build_object_specs(
    *,
    scene: Scene,
    candidates: dict[str, CandidateLayerPayload],
) -> list[ObjectRenderSpec]:
    answer_region_ids = set(scene.answer.answer_region_ids)
    specs: list[ObjectRenderSpec] = []
    object_index = 1
    for layer in sorted(scene.layers.items, key=lambda item: item.order):
        region_id = layer.source_region_id
        if region_id is None or region_id not in answer_region_ids or layer.bbox is None:
            continue
        candidate = candidates.get(region_id, {})
        source_ref = resolve_object_source_ref(candidate=candidate, fallback=layer.image_ref)
        if source_ref is None:
            continue
        prompt = str(candidate.get("object_prompt_resolved") or "").strip()
        negative_prompt = str(candidate.get("object_negative_prompt_resolved") or "").strip()
        display_name = compose_display_name(
            prompt=prompt,
            negative_prompt=negative_prompt,
        ) or f"object {object_index}"
        specs.append(
            ObjectRenderSpec(
                object_id=f"object_{object_index:02d}",
                lottie_id=f"lottie_{object_index:02d}",
                region_id=region_id,
                layer_id=layer.layer_id,
                name=display_name,
                title=display_name,
                prompt=prompt,
                order=int(layer.order),
                bbox={
                    "x": float(layer.bbox.x),
                    "y": float(layer.bbox.y),
                    "w": float(layer.bbox.w),
                    "h": float(layer.bbox.h),
                },
                source_ref=source_ref,
            )
        )
        object_index += 1
    return specs


def resolve_object_source_ref(
    *,
    candidate: CandidateLayerPayload,
    fallback: str | None = None,
) -> str | None:
    for key in (
        "layer_image_ref",
        "processed_object_image_ref",
        "object_image_ref",
        "candidate_image_ref",
    ):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    if isinstance(fallback, str) and fallback:
        return fallback
    return None


def file_name(path: str | Path) -> str:
    return Path(str(path)).name


def bbox_center(bbox: BBoxPayload) -> tuple[float, float]:
    return (bbox["x"] + (bbox["w"] / 2.0), bbox["y"] + (bbox["h"] / 2.0))
