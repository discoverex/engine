from __future__ import annotations

from math import sqrt

from PIL import Image, ImageFilter, ImageOps

from .common import clamp01
from .pixels import gray_pixel


def compute_saliency_lift(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
) -> tuple[float, dict[str, float]]:
    x1, y1, x2, y2 = bbox
    region = image.crop((x1, y1, x2, y2))
    surround = surrounding_patch(image, bbox)
    region_contrast = luma_stddev(region)
    surround_contrast = luma_stddev(surround)
    region_edges = edge_density(region)
    surround_edges = edge_density(surround)
    contrast_lift = clamp01((region_contrast - surround_contrast) / 64.0 + 0.5)
    edge_lift = clamp01((region_edges - surround_edges) / 96.0 + 0.5)
    saliency = clamp01(max(0.0, (contrast_lift + edge_lift) / 2.0 - 0.5) * 2.0)
    return saliency, {
        "region_contrast": round(region_contrast, 4),
        "surround_contrast": round(surround_contrast, 4),
        "region_edge_density": round(region_edges, 4),
        "surround_edge_density": round(surround_edges, 4),
    }


def surrounding_patch(
    image: Image.Image, bbox: tuple[int, int, int, int]
) -> Image.Image:
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


def luma_stddev(image: Image.Image) -> float:
    gray = image.convert("L")
    luma = [
        gray_pixel(gray, x, y)
        for y in range(gray.height)
        for x in range(gray.width)
    ]
    if not luma:
        return 0.0
    mean = sum(luma) / len(luma)
    variance = sum((pixel - mean) ** 2 for pixel in luma) / len(luma)
    return sqrt(variance)


def edge_density(image: Image.Image) -> float:
    edged = ImageOps.grayscale(image).filter(ImageFilter.FIND_EDGES)
    values = [
        gray_pixel(edged, x, y)
        for y in range(edged.height)
        for x in range(edged.width)
    ]
    if not values:
        return 0.0
    return sum(values) / len(values)
