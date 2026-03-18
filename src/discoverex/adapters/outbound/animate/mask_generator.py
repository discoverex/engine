"""MaskGenerationPort implementation — binary mask for WAN moving zone.

Mask convention (SetLatentNoiseMask):
    Black (0)   = moving zone  → KSampler generates freely
    White (255) = fixed zone   → original pixels preserved

Dependencies: PIL only.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

BLUR_RADIUS_RATIO = 0.03


class PilMaskGenerator:
    """Generate binary mask PNG from moving_zone bounding box."""

    def generate(
        self,
        image_path: Path,
        moving_zone: list[float],
        output_dir: Path | None = None,
    ) -> Path:
        img = Image.open(image_path)
        w, h = img.size

        x1, y1, x2, y2 = moving_zone
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)

        mask = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(mask)
        draw.rectangle([px1, py1, px2, py2], fill=0)

        blur_r = max(2, int(min(w, h) * BLUR_RADIUS_RATIO))
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_r))

        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp())
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(image_path).stem
        mask_path = output_dir / f"{stem}_mask.png"
        mask.save(mask_path, "PNG")

        logger.info(
            f"[MaskGen] mask created: {mask_path} "
            f"(zone=[{px1},{py1},{px2},{py2}] blur={blur_r}px)"
        )
        return mask_path
