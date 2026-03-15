from __future__ import annotations

from pathlib import Path
from typing import Any


def load_image_rgb(path: str | Path) -> Any:
    from PIL import Image  # type: ignore

    return Image.open(path).convert("RGB")


def save_image(image: Any, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out


def sanitize_bbox(
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x, y, w, h = [float(v) for v in bbox]
    left = max(0, min(int(x), width - 1))
    top = max(0, min(int(y), height - 1))
    right = max(left + 1, min(int(x + max(1.0, w)), width))
    bottom = max(top + 1, min(int(y + max(1.0, h)), height))
    return left, top, right, bottom


def crop_bbox(image: Any, bbox: tuple[int, int, int, int]) -> Any:
    return image.crop(bbox)


def expand_bbox(
    bbox: tuple[int, int, int, int],
    *,
    padding: int,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    pad = max(0, int(padding))
    return (
        max(0, left - pad),
        max(0, top - pad),
        min(width, right + pad),
        min(height, bottom + pad),
    )


def resize_image(image: Any, size: tuple[int, int]) -> Any:
    return image.resize(size)


def apply_patch(image: Any, patch: Any, bbox: tuple[int, int, int, int]) -> Any:
    left, top, right, bottom = bbox
    region_w = max(1, right - left)
    region_h = max(1, bottom - top)
    resized_patch = patch.resize((region_w, region_h))
    composited = image.copy()
    composited.paste(resized_patch, (left, top))
    return composited


def apply_alpha_patch(image: Any, patch: Any, bbox: tuple[int, int, int, int]) -> Any:
    left, top, right, bottom = bbox
    region_w = max(1, right - left)
    region_h = max(1, bottom - top)
    rgba_patch = patch.convert("RGBA").resize((region_w, region_h))
    composited = image.convert("RGBA")
    composited.alpha_composite(rgba_patch, (left, top))
    return composited.convert("RGB")
