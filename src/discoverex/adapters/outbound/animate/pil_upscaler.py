"""PIL-based image upscaler — Lanczos for general images, nearest for pixel art."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class PilImageUpscaler:
    """ImageUpscalerPort implementation using PIL resampling.

    Lanczos: high-quality interpolation for illustrations, photos, vectors.
    Nearest: pixel-perfect scaling for pixel art (no blur).
    """

    def upscale(
        self, image: Path, scale_factor: float, art_style: str = "illustration",
    ) -> Path:
        src = Image.open(image)
        ow, oh = src.size
        new_w = int(ow * scale_factor)
        new_h = int(oh * scale_factor)

        resampling = (
            Image.Resampling.NEAREST
            if art_style == "pixel_art"
            else Image.Resampling.LANCZOS
        )
        method_name = "nearest" if art_style == "pixel_art" else "lanczos"

        upscaled = src.resize((new_w, new_h), resampling)

        out_path = image.parent / f"{image.stem}_upscaled{image.suffix}"
        upscaled.save(out_path)

        logger.info(
            "[Upscaler] %dx%d -> %dx%d (x%.1f, %s)",
            ow, oh, new_w, new_h, scale_factor, method_name,
        )
        return out_path
