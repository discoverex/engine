"""Animate pipeline image preprocessing.

White-anchor background cleaning and canvas padding for WAN I2V input.
Pure domain logic — external dependencies are PIL only (already in engine).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


def white_anchor(image: Image.Image, tolerance: int = 30) -> Image.Image:
    """Clean background to pure white and sharpen character edges.

    Only applied when background is bright (mean > 200).
    Uses flood-fill from border to identify connected background pixels.
    """
    import numpy as np
    from scipy import ndimage

    arr = np.array(image.convert("RGB"))
    h, w = arr.shape[:2]

    bs = max(3, h // 20)
    border = np.concatenate([
        arr[:bs, :].reshape(-1, 3),
        arr[-bs:, :].reshape(-1, 3),
        arr[:, :bs].reshape(-1, 3),
        arr[:, -bs:].reshape(-1, 3),
    ])
    bg_mean = border.mean(axis=0)

    if bg_mean.mean() < 200:
        return image

    is_bg_color = np.all(np.abs(arr.astype(int) - bg_mean) < tolerance, axis=2)
    labeled, _ = ndimage.label(is_bg_color)
    border_labels = (
        set(labeled[0, :].tolist())
        | set(labeled[-1, :].tolist())
        | set(labeled[:, 0].tolist())
        | set(labeled[:, -1].tolist())
    )
    border_labels.discard(0)
    bg_mask = np.zeros((h, w), dtype=bool)
    for lbl in border_labels:
        bg_mask |= labeled == lbl

    result = arr.copy()
    result[bg_mask] = 255

    sharpened = Image.fromarray(result).filter(
        ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3)
    )
    s_arr = np.array(sharpened)
    s_arr[bg_mask] = 255

    return Image.fromarray(s_arr)


def _detect_bg_color(src: Image.Image) -> tuple[int, int, int]:
    """Detect optimal background color based on character brightness.

    If the character has many bright/white pixels → use black background.
    Otherwise → use white background (default).
    """
    import numpy as np

    arr = np.array(src)
    if arr.shape[2] == 4:
        has_transparency = (arr[:, :, 3] < 128).sum() > arr.shape[0] * arr.shape[1] * 0.1
        if has_transparency:
            opaque = arr[:, :, 3] > 128
            pixels = arr[opaque, :3]
            best = _find_best_bg_color(pixels)
            logger.info("[Preprocess] 투명배경 → 최적 배경색 %s", best)
            return best
    logger.info("[Preprocess] 기본 → 흰색 배경")
    return (255, 255, 255)


_BG_CANDIDATES = [
    ("chroma_green", (0, 177, 64)),
    ("white", (255, 255, 255)),
    ("black", (0, 0, 0)),
    ("lime", (0, 255, 0)),
    ("magenta", (255, 0, 255)),
]


def _find_best_bg_color(pixels: Any) -> tuple[int, int, int]:
    """Find background color distant from character pixels.

    Prioritizes chroma_green if distance > 100, since WAN preserves green
    backgrounds better than magenta. Falls back to max distance otherwise.
    """
    import numpy as np

    best_color = (255, 255, 255)
    best_dist = -1
    for name, color in _BG_CANDIDATES:
        min_dist = int(np.abs(pixels.astype(int) - list(color)).sum(axis=1).min())
        if name == "chroma_green" and min_dist > 100:
            return color
        if min_dist > best_dist:
            best_dist = min_dist
            best_color = color
    return best_color


def preprocess_image_simple(
    image_path: str | Path,
    output_path: str | Path,
    width: int = 480,
    height: int = 480,
    scale: float = 0.65,
    headroom_top: float = 0.18,
    headroom_bottom: float = 0.15,
) -> tuple[Path, str]:
    """Preprocess image with auto background color selection.

    Returns (output_path, bg_type) where bg_type is "solid" or "dark".
    """
    src = Image.open(image_path).convert("RGBA")
    ow, oh = src.size

    if ow <= width and oh <= height:
        target_w, target_h = ow, oh
        src_resized = src
    else:
        target_w = int(width * scale)
        ratio = target_w / ow
        target_h = int(oh * ratio)
        if target_h > height:
            target_h = int(height * scale)
            ratio = target_h / oh
            target_w = int(ow * ratio)
        src_resized = src.resize((target_w, target_h), Image.Resampling.LANCZOS)

    bg_rgb = _detect_bg_color(src)
    _BG_TYPE_MAP = {(255, 255, 255): "solid", (0, 0, 0): "dark"}
    bg_type = _BG_TYPE_MAP.get(bg_rgb, "chroma")
    canvas = Image.new("RGBA", (width, height), (*bg_rgb, 255))

    x = (width - target_w) // 2
    y = int(height * headroom_top)
    if y + target_h > height - int(height * headroom_bottom):
        y = max(0, height - target_h - int(height * headroom_bottom))

    canvas.paste(src_resized, (x, y), src_resized)
    if bg_type == "solid":
        result = white_anchor(canvas.convert("RGB"))
    else:
        result = canvas.convert("RGB")

    out = Path(output_path)
    result.save(out)

    scaled_str = "원본유지" if (target_w == ow and target_h == oh) else "축소"
    logger.info(
        f"[Preprocess] {ow}x{oh} -> {target_w}x{target_h} ({scaled_str}) "
        f"pos=({x},{y}) canvas={width}x{height} bg={bg_type}"
    )
    return out, bg_type
