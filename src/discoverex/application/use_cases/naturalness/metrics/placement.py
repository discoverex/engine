from __future__ import annotations

from PIL import Image

from discoverex.domain.naturalness import NaturalnessRegionInput

from .common import clamp01
from .seams import color_delta_for_bbox


def compute_placement_fit(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    item: NaturalnessRegionInput,
) -> tuple[float, dict[str, float | str]]:
    context_match = 1.0 - color_delta_for_bbox(image, bbox)
    placement_score = clamp01(
        item.placement_score if item.placement_score is not None else context_match
    )
    fit = clamp01(0.7 * placement_score + 0.3 * context_match)
    return fit, {
        "placement_score_input": round(placement_score, 4),
        "placement_context_match": round(context_match, 4),
        "mask_source": item.mask_source or "",
    }
