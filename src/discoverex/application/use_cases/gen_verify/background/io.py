from __future__ import annotations

from pathlib import Path
from typing import Any


def read_background_image_size(
    *,
    image_path: Path,
) -> dict[str, Any]:
    from PIL import Image

    with Image.open(image_path).convert("RGB") as image:
        return {
            "path": image_path,
            "width": image.width,
            "height": image.height,
        }
