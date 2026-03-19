"""Animate pipeline image preprocessing.

White-anchor background cleaning and canvas padding for WAN I2V input.
Pure domain logic — external dependencies are PIL only (already in engine).
"""

from __future__ import annotations

import logging
from pathlib import Path

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


def preprocess_image_simple(
    image_path: str | Path,
    output_path: str | Path,
    width: int = 480,
    height: int = 480,
    scale: float = 0.65,
    headroom_top: float = 0.18,
    headroom_bottom: float = 0.15,
) -> Path:
    """Preprocess image with white background for WAN I2V input."""
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

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))

    x = (width - target_w) // 2
    y = int(height * headroom_top)
    if y + target_h > height - int(height * headroom_bottom):
        y = max(0, height - target_h - int(height * headroom_bottom))

    canvas.paste(src_resized, (x, y), src_resized)
    result = white_anchor(canvas.convert("RGB"))

    out = Path(output_path)
    result.save(out)

    scaled_str = "원본유지" if (target_w == ow and target_h == oh) else "축소"
    logger.info(
        f"[Preprocess] {ow}x{oh} -> {target_w}x{target_h} ({scaled_str}) "
        f"pos=({x},{y}) canvas={width}x{height}"
    )
    return out
