from __future__ import annotations

from typing import Any

from .runtime import BackendRuntime


class Sam2MaskRefiner:
    def __init__(self, *, model_id: str, runtime: BackendRuntime) -> None:
        self.model_id = model_id
        self.runtime = runtime
        self._predictor: Any | None = None

    def refine(self, *, image: Any, fallback_mask: Any) -> Any:
        import numpy as np
        from PIL import Image  # type: ignore
        from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore

        if not self.model_id.strip():
            raise RuntimeError("SAM2 model_id is required")
        if self._predictor is None:
            self._predictor = SAM2ImagePredictor.from_pretrained(self.model_id)
        bbox = fallback_mask.getbbox()
        if bbox is None:
            return fallback_mask
        self._predictor.set_image(np.array(image.convert("RGB")))
        masks, scores, _ = self._predictor.predict(box=np.array([bbox], dtype=np.float32), multimask_output=True)
        if len(masks) == 0:
            return fallback_mask
        mask = Image.fromarray((masks[max(range(len(scores)), key=lambda idx: float(scores[idx]))].astype("uint8") * 255), mode="L")
        return fallback_mask if mask.getbbox() is None else mask
