from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from .image_patch_ops import save_image


class SamObjectMaskExtractor:
    def __init__(self, *, device: str = "cpu", dtype: str = "float16") -> None:
        self.device = device
        self.dtype = dtype
        self._predictor: Any | None = None

    def extract(
        self,
        *,
        image_path: str | Path,
        output_prefix: str | Path,
    ) -> dict[str, str | Path]:
        loaded = self._load_image(image_path)
        image = loaded["rgb"]
        alpha = loaded.get("alpha")
        raw_alpha_path: Path | None = None
        if alpha is not None and alpha.getbbox() is not None:
            mask = alpha
            object_rgba = image.convert("RGBA")
            object_rgba.putalpha(mask)
            mask_source = "layerdiffuse_alpha"
        else:
            mask = self._predict_mask(image)
            object_rgba = image.convert("RGBA")
            object_rgba.putalpha(mask)
            mask_source = "mask_extractor"
        prefix = Path(output_prefix)
        object_path = save_image(object_rgba, prefix.with_suffix(".object.png"))
        mask_path = save_image(mask, prefix.with_suffix(".mask.png"))
        if alpha is not None and alpha.getbbox() is not None:
            raw_alpha_path = save_image(alpha, prefix.with_suffix(".raw-alpha-mask.png"))
        return {
            "object": object_path,
            "mask": mask_path,
            "raw_alpha_mask": raw_alpha_path or mask_path,
            "mask_source": mask_source,
        }

    def unload(self) -> None:
        self._predictor = None

    def _load_image(self, image_path: str | Path) -> dict[str, Any]:
        from PIL import Image  # type: ignore

        with Image.open(image_path) as loaded:
            rgba = loaded.convert("RGBA")
            alpha = rgba.getchannel("A")
            return {
                "rgb": rgba.convert("RGB"),
                "alpha": alpha if alpha.getbbox() is not None else None,
            }

    def _predict_mask(self, image: Any) -> Any:
        try:
            import numpy as np
            import torch  # type: ignore
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=".*timm.models.layers.*deprecated.*",
                    category=FutureWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message=".*timm.models.registry.*deprecated.*",
                    category=FutureWarning,
                )
                from mobile_sam import SamPredictor, sam_model_registry  # type: ignore
            from PIL import Image  # type: ignore
        except Exception:
            return self._fallback_mask(image)

        if self._predictor is None:
            dtype = torch.float16 if self.dtype == "float16" else torch.float32
            sam = sam_model_registry["vit_t"](checkpoint=None)
            sam = sam.to(device=self.device, dtype=dtype)
            sam.eval()
            self._predictor = SamPredictor(sam)

        predictor = self._predictor
        if predictor is None:
            return self._fallback_mask(image)

        rgb = np.array(image)
        predictor.set_image(rgb)
        width, height = image.size
        margin_x = max(2, int(width * 0.1))
        margin_y = max(2, int(height * 0.1))
        box = np.array([margin_x, margin_y, width - margin_x, height - margin_y])
        point_coords = np.array([[width / 2.0, height / 2.0]])
        point_labels = np.array([1])
        try:
            masks, scores, _ = predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                box=box,
                multimask_output=True,
            )
        except Exception:
            return self._fallback_mask(image)

        if len(masks) == 0:
            return self._fallback_mask(image)
        best_idx = max(range(len(scores)), key=lambda idx: float(scores[idx]))
        best_mask = masks[best_idx].astype("uint8") * 255
        mask_image = Image.fromarray(best_mask, mode="L")
        if mask_image.getbbox() is None:
            return self._fallback_mask(image)
        return mask_image

    def _fallback_mask(self, image: Any) -> Any:
        from PIL import Image, ImageFilter, ImageOps  # type: ignore

        gray = image.convert("L")
        mask = ImageOps.autocontrast(gray)
        mask = mask.point(lambda value: 255 if value > 12 else 0)
        mask = mask.filter(ImageFilter.MaxFilter(5))
        if mask.getbbox() is None:
            return Image.new("L", image.size, color=255)
        return mask
