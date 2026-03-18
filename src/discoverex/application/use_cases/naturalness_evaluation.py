from __future__ import annotations

from math import sqrt
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

from discoverex.domain.naturalness import (
    NaturalnessEvaluation,
    NaturalnessRegionInput,
    NaturalnessRegionScore,
)
from discoverex.domain.scene import Scene

_MIN_RING_WIDTH = 3
_MAX_RING_WIDTH = 8


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
        inputs.append(
            NaturalnessRegionInput(
                region_id=region.region_id,
                final_image_ref=final_image_ref,
                selected_bbox={
                    "x": float(bbox_dict["x"]),
                    "y": float(bbox_dict["y"]),
                    "w": float(bbox_dict["w"]),
                    "h": float(bbox_dict["h"]),
                },
                object_image_ref=_as_str(attrs.get("object_image_ref")),
                object_mask_ref=_as_str(attrs.get("object_mask_ref")),
                patch_image_ref=_as_str(attrs.get("patch_image_ref")),
                precomposited_image_ref=_as_str(attrs.get("precomposited_image_ref")),
                blend_mask_ref=_as_str(attrs.get("blend_mask_ref")),
                placement_score=_as_float(attrs.get("placement_score")),
                variant_manifest_ref=_as_str(attrs.get("variant_manifest_ref")),
                mask_source=_as_str(attrs.get("mask_source")),
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
    overall = sum(item.natural_hidden_score for item in scores) / len(scores) if scores else 0.0
    return NaturalnessEvaluation(
        scene_id=scene_id,
        version_id=version_id,
        overall_score=round(overall, 4),
        regions=scores,
        summary={
            "region_count": len(scores),
            "avg_placement_fit": _average(score.placement_fit for score in scores),
            "avg_seam_visibility": _average(score.seam_visibility for score in scores),
            "avg_saliency_lift": _average(score.saliency_lift for score in scores),
        },
    )


def evaluate_region_naturalness(item: NaturalnessRegionInput) -> NaturalnessRegionScore:
    final_path = Path(item.final_image_ref)
    if not final_path.exists():
        raise FileNotFoundError(f"final image not found: {final_path}")
    with Image.open(final_path).convert("RGB") as final_image:
        bbox = _sanitize_bbox(item.selected_bbox, final_image.width, final_image.height)
        placement_fit, placement_signals = _compute_placement_fit(final_image, bbox, item)
        seam_visibility, seam_signals = _compute_seam_visibility(final_image, bbox, item)
        saliency_lift, saliency_signals = _compute_saliency_lift(final_image, bbox)
    score = (
        0.45 * placement_fit
        + 0.35 * (1.0 - seam_visibility)
        + 0.20 * (1.0 - saliency_lift)
    )
    return NaturalnessRegionScore(
        region_id=item.region_id,
        natural_hidden_score=round(_clamp01(score), 4),
        placement_fit=round(placement_fit, 4),
        seam_visibility=round(seam_visibility, 4),
        saliency_lift=round(saliency_lift, 4),
        diagnosis_signals={
            **placement_signals,
            **seam_signals,
            **saliency_signals,
        },
    )


def _compute_placement_fit(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    item: NaturalnessRegionInput,
) -> tuple[float, dict[str, float | str]]:
    context_match = 1.0 - _color_delta_for_bbox(image, bbox)
    placement_score = _clamp01(item.placement_score if item.placement_score is not None else context_match)
    fit = _clamp01(0.7 * placement_score + 0.3 * context_match)
    return fit, {
        "placement_score_input": round(placement_score, 4),
        "placement_context_match": round(context_match, 4),
        "mask_source": item.mask_source or "",
    }


def _compute_seam_visibility(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    item: NaturalnessRegionInput,
) -> tuple[float, dict[str, float]]:
    inner_ring, outer_ring = _ring_masks(image.size, bbox)
    color_delta = _masked_color_delta(image, inner_ring, outer_ring)
    edge_delta = _masked_edge_delta(image, inner_ring, outer_ring)
    seam = _clamp01(0.55 * color_delta + 0.45 * edge_delta)
    if item.blend_mask_ref:
        seam *= 0.95
    return seam, {
        "seam_color_delta": round(color_delta, 4),
        "seam_edge_delta": round(edge_delta, 4),
    }


def _compute_saliency_lift(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
) -> tuple[float, dict[str, float]]:
    x1, y1, x2, y2 = bbox
    region = image.crop((x1, y1, x2, y2))
    surround = _surrounding_patch(image, bbox)
    region_contrast = _luma_stddev(region)
    surround_contrast = _luma_stddev(surround)
    region_edges = _edge_density(region)
    surround_edges = _edge_density(surround)
    contrast_lift = _clamp01((region_contrast - surround_contrast) / 64.0 + 0.5)
    edge_lift = _clamp01((region_edges - surround_edges) / 96.0 + 0.5)
    saliency = _clamp01(max(0.0, (contrast_lift + edge_lift) / 2.0 - 0.5) * 2.0)
    return saliency, {
        "region_contrast": round(region_contrast, 4),
        "surround_contrast": round(surround_contrast, 4),
        "region_edge_density": round(region_edges, 4),
        "surround_edge_density": round(surround_edges, 4),
    }


def _color_delta_for_bbox(image: Image.Image, bbox: tuple[int, int, int, int]) -> float:
    inner_ring, outer_ring = _ring_masks(image.size, bbox)
    return _masked_color_delta(image, inner_ring, outer_ring)


def _masked_color_delta(image: Image.Image, first_mask: Image.Image, second_mask: Image.Image) -> float:
    first_mean = _masked_rgb_mean(image, first_mask)
    second_mean = _masked_rgb_mean(image, second_mask)
    distance = sqrt(
        (first_mean[0] - second_mean[0]) ** 2
        + (first_mean[1] - second_mean[1]) ** 2
        + (first_mean[2] - second_mean[2]) ** 2
    )
    return _clamp01(distance / (sqrt(3.0) * 255.0))


def _masked_edge_delta(image: Image.Image, first_mask: Image.Image, second_mask: Image.Image) -> float:
    edged = ImageOps.grayscale(image).filter(ImageFilter.FIND_EDGES)
    first_mean = _masked_gray_mean(edged, first_mask)
    second_mean = _masked_gray_mean(edged, second_mask)
    return _clamp01(abs(first_mean - second_mean) / 255.0)


def _ring_masks(
    size: tuple[int, int],
    bbox: tuple[int, int, int, int],
) -> tuple[Image.Image, Image.Image]:
    from PIL import ImageDraw

    width, height = size
    x1, y1, x2, y2 = bbox
    ring_width = max(_MIN_RING_WIDTH, min(_MAX_RING_WIDTH, min(x2 - x1, y2 - y1) // 6 or _MIN_RING_WIDTH))
    inner = Image.new("L", (width, height), color=0)
    outer = Image.new("L", (width, height), color=0)
    inner_draw = ImageDraw.Draw(inner)
    outer_draw = ImageDraw.Draw(outer)
    inner_draw.rectangle((x1, y1, x2, y2), outline=255, width=ring_width)
    outer_bbox = (
        max(0, x1 - ring_width),
        max(0, y1 - ring_width),
        min(width - 1, x2 + ring_width),
        min(height - 1, y2 + ring_width),
    )
    outer_draw.rectangle(outer_bbox, outline=255, width=ring_width)
    outer = ImageChops.subtract(outer, inner)
    return inner, outer


def _surrounding_patch(image: Image.Image, bbox: tuple[int, int, int, int]) -> Image.Image:
    x1, y1, x2, y2 = bbox
    pad_x = max(4, (x2 - x1) // 2)
    pad_y = max(4, (y2 - y1) // 2)
    return image.crop(
        (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(image.width, x2 + pad_x),
            min(image.height, y2 + pad_y),
        )
    )


def _masked_rgb_mean(image: Image.Image, mask: Image.Image) -> tuple[float, float, float]:
    image_rgb = image.convert("RGB")
    mask_l = mask.convert("L")
    total = [0.0, 0.0, 0.0]
    weight = 0.0
    for (r, g, b), m in zip(list(image_rgb.getdata()), list(mask_l.getdata()), strict=False):
        if m <= 0:
            continue
        total[0] += r
        total[1] += g
        total[2] += b
        weight += 1.0
    if weight <= 0.0:
        return (0.0, 0.0, 0.0)
    return (total[0] / weight, total[1] / weight, total[2] / weight)


def _masked_gray_mean(image: Image.Image, mask: Image.Image) -> float:
    image_l = image.convert("L")
    mask_l = mask.convert("L")
    total = 0.0
    weight = 0.0
    for pixel, m in zip(list(image_l.getdata()), list(mask_l.getdata()), strict=False):
        if m <= 0:
            continue
        total += pixel
        weight += 1.0
    if weight <= 0.0:
        return 0.0
    return total / weight


def _luma_stddev(image: Image.Image) -> float:
    luma = list(image.convert("L").getdata())
    if not luma:
        return 0.0
    mean = sum(luma) / len(luma)
    variance = sum((pixel - mean) ** 2 for pixel in luma) / len(luma)
    return sqrt(variance)


def _edge_density(image: Image.Image) -> float:
    edged = ImageOps.grayscale(image).filter(ImageFilter.FIND_EDGES)
    values = list(edged.getdata())
    if not values:
        return 0.0
    return sum(values) / len(values)


def _sanitize_bbox(bbox: dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(float(bbox["x"])))))
    y1 = max(0, min(height - 1, int(round(float(bbox["y"])))))
    x2 = max(x1 + 1, min(width, int(round(float(bbox["x"]) + float(bbox["w"])))))
    y2 = max(y1 + 1, min(height, int(round(float(bbox["y"]) + float(bbox["h"])))))
    return (x1, y1, x2, y2)


def _average(values: object) -> float:
    items = list(values)
    return round(sum(items) / len(items), 4) if items else 0.0


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 1.0))


def _as_str(value: object) -> str | None:
    return str(value) if isinstance(value, (str, Path)) and str(value) else None


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
