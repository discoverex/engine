from __future__ import annotations

from math import sqrt

from PIL import Image, ImageChops, ImageFilter, ImageOps

from discoverex.domain.naturalness import NaturalnessRegionInput

from .common import clamp01
from .pixels import masked_gray_mean, masked_rgb_mean

_MIN_RING_WIDTH = 3
_MAX_RING_WIDTH = 8


def compute_seam_visibility(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    item: NaturalnessRegionInput,
) -> tuple[float, dict[str, float]]:
    inner_ring, outer_ring = ring_masks(image.size, bbox)
    color_delta = masked_color_delta(image, inner_ring, outer_ring)
    edge_delta = masked_edge_delta(image, inner_ring, outer_ring)
    seam = clamp01(0.55 * color_delta + 0.45 * edge_delta)
    if item.blend_mask_ref:
        seam *= 0.95
    return seam, {
        "seam_color_delta": round(color_delta, 4),
        "seam_edge_delta": round(edge_delta, 4),
    }


def color_delta_for_bbox(image: Image.Image, bbox: tuple[int, int, int, int]) -> float:
    inner_ring, outer_ring = ring_masks(image.size, bbox)
    return masked_color_delta(image, inner_ring, outer_ring)


def masked_color_delta(
    image: Image.Image, first_mask: Image.Image, second_mask: Image.Image
) -> float:
    first_mean = masked_rgb_mean(image, first_mask)
    second_mean = masked_rgb_mean(image, second_mask)
    distance = sqrt(
        (first_mean[0] - second_mean[0]) ** 2
        + (first_mean[1] - second_mean[1]) ** 2
        + (first_mean[2] - second_mean[2]) ** 2
    )
    return clamp01(distance / (sqrt(3.0) * 255.0))


def masked_edge_delta(
    image: Image.Image, first_mask: Image.Image, second_mask: Image.Image
) -> float:
    edged = ImageOps.grayscale(image).filter(ImageFilter.FIND_EDGES)
    first_mean = masked_gray_mean(edged, first_mask)
    second_mean = masked_gray_mean(edged, second_mask)
    return clamp01(abs(first_mean - second_mean) / 255.0)


def ring_masks(
    size: tuple[int, int],
    bbox: tuple[int, int, int, int],
) -> tuple[Image.Image, Image.Image]:
    from PIL import ImageDraw

    width, height = size
    x1, y1, x2, y2 = bbox
    ring_width = max(
        _MIN_RING_WIDTH,
        min(_MAX_RING_WIDTH, min(x2 - x1, y2 - y1) // 6 or _MIN_RING_WIDTH),
    )
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
