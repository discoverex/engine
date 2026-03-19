from __future__ import annotations

from PIL import Image

from discoverex.domain.naturalness import (
    NaturalnessEvaluation,
    NaturalnessRegionInput,
    NaturalnessRegionScore,
    NaturalnessSummary,
    SelectedBBox,
)
from discoverex.domain.scene import Scene

from .metrics import (
    as_float,
    as_str,
    average,
    clamp01,
    compute_placement_fit,
    compute_saliency_lift,
    compute_seam_visibility,
    sanitize_bbox,
)


def collect_naturalness_inputs(scene: Scene) -> list[NaturalnessRegionInput]:
    inputs: list[NaturalnessRegionInput] = []
    final_image_ref = scene.composite.final_image_ref
    for region in scene.regions:
        attrs = region.attributes
        bbox_dict = attrs.get("selected_bbox")
        if not isinstance(bbox_dict, dict):
            bbox = region.geometry.bbox
            bbox_dict = {
                "x": bbox.x,
                "y": bbox.y,
                "w": bbox.w,
                "h": bbox.h,
            }
        if not final_image_ref:
            continue
        try:
            selected_bbox: SelectedBBox = {
                "x": float(bbox_dict["x"]),
                "y": float(bbox_dict["y"]),
                "w": float(bbox_dict["w"]),
                "h": float(bbox_dict["h"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        inputs.append(
            NaturalnessRegionInput(
                region_id=region.region_id,
                final_image_ref=final_image_ref,
                selected_bbox=selected_bbox,
                object_image_ref=as_str(attrs.get("object_image_ref")),
                object_mask_ref=as_str(attrs.get("object_mask_ref")),
                patch_image_ref=as_str(attrs.get("patch_image_ref")),
                precomposited_image_ref=as_str(attrs.get("precomposited_image_ref")),
                blend_mask_ref=as_str(attrs.get("blend_mask_ref")),
                placement_score=as_float(attrs.get("placement_score")),
                variant_manifest_ref=as_str(attrs.get("variant_manifest_ref")),
                mask_source=as_str(attrs.get("mask_source")),
            )
        )
    return inputs


def evaluate_scene_naturalness(scene: Scene) -> NaturalnessEvaluation:
    return evaluate_naturalness_inputs(
        collect_naturalness_inputs(scene),
        scene_id=scene.meta.scene_id,
        version_id=scene.meta.version_id,
    )


def evaluate_naturalness_inputs(
    inputs: list[NaturalnessRegionInput],
    *,
    scene_id: str | None = None,
    version_id: str | None = None,
) -> NaturalnessEvaluation:
    scores = [evaluate_region_naturalness(item) for item in inputs]
    overall = (
        sum(item.natural_hidden_score for item in scores) / len(scores)
        if scores
        else 0.0
    )
    summary: NaturalnessSummary = {
        "region_count": len(scores),
        "avg_placement_fit": average(score.placement_fit for score in scores),
        "avg_seam_visibility": average(score.seam_visibility for score in scores),
        "avg_saliency_lift": average(score.saliency_lift for score in scores),
    }
    return NaturalnessEvaluation(
        scene_id=scene_id,
        version_id=version_id,
        overall_score=round(overall, 4),
        regions=scores,
        summary=summary,
    )


def evaluate_region_naturalness(item: NaturalnessRegionInput) -> NaturalnessRegionScore:
    with Image.open(item.final_image_ref).convert("RGB") as final_image:
        bbox = sanitize_bbox(
            item.selected_bbox,
            final_image.width,
            final_image.height,
        )
        placement_fit, placement_signals = compute_placement_fit(final_image, bbox, item)
        seam_visibility, seam_signals = compute_seam_visibility(final_image, bbox, item)
        saliency_lift, saliency_signals = compute_saliency_lift(final_image, bbox)
    score = (
        0.45 * placement_fit
        + 0.35 * (1.0 - seam_visibility)
        + 0.20 * (1.0 - saliency_lift)
    )
    return NaturalnessRegionScore(
        region_id=item.region_id,
        natural_hidden_score=round(clamp01(score), 4),
        placement_fit=round(placement_fit, 4),
        seam_visibility=round(seam_visibility, 4),
        saliency_lift=round(saliency_lift, 4),
        diagnosis_signals={
            **placement_signals,
            **seam_signals,
            **saliency_signals,
        },
    )
