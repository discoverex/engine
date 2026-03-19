from __future__ import annotations

from typing import Any

from ..runtime import normalize_dtype
from .runtime import BackendRuntime


class Rmbg20MaskRefiner:
    def __init__(self, *, model_id: str, revision: str = "main", runtime: BackendRuntime) -> None:
        self.model_id = model_id
        self.revision = revision
        self.runtime = runtime
        self._model: Any | None = None
        self._image_processor: Any | None = None

    def _lazy_load(self) -> None:
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                AutoImageProcessor,
                AutoModelForImageSegmentation,
            )
        except Exception as exc:
            raise RuntimeError("RMBG 2.0 runtime unavailable during model load") from exc
        if self._image_processor is None:
            self._image_processor = AutoImageProcessor.from_pretrained(self.model_id, revision=self.revision, use_fast=True)  # type: ignore[no-untyped-call]
        if self._model is None:
            device_str = str(self.runtime.device)
            torch_dtype = torch.float32 if device_str.startswith("cpu") else normalize_dtype(self.runtime.dtype, torch)
            model = AutoModelForImageSegmentation.from_pretrained(  # type: ignore[no-untyped-call]
                self.model_id,
                revision=self.revision,
                trust_remote_code=True,
                dtype=torch_dtype,
            )
            model = model.to(self.runtime.device)
            if device_str.startswith("cpu"):
                model = model.float()
            model.eval()
            self._model = model

    def _extract_prediction(self, outputs: Any) -> Any:
        for name in ("predicted_alpha", "logits", "preds"):
            pred = getattr(outputs, name, None)
            if pred is not None:
                return pred
        if isinstance(outputs, (tuple, list)) and outputs:
            return outputs[0]
        raise RuntimeError("RMBG 2.0 returned no usable alpha prediction")

    def _normalize_alpha(self, pred: Any) -> Any:
        import torch  # type: ignore

        if not isinstance(pred, torch.Tensor):
            raise RuntimeError("RMBG 2.0 prediction is not a tensor")
        if pred.ndim == 4:
            alpha = pred[0][0]
        elif pred.ndim == 3:
            alpha = pred[0]
        elif pred.ndim == 2:
            alpha = pred
        else:
            raise RuntimeError(f"Unexpected RMBG 2.0 prediction shape: {tuple(pred.shape)}")
        alpha = alpha.squeeze()
        if alpha.ndim != 2:
            raise RuntimeError(f"Unexpected RMBG 2.0 alpha shape after squeeze: {tuple(alpha.shape)}")
        return alpha.detach().float().cpu().clamp(0, 1)

    def refine(self, *, image: Any, fallback_mask: Any) -> Any:
        import numpy as np  # type: ignore
        import torch  # type: ignore
        from PIL import Image  # type: ignore
        from torchvision.transforms.functional import to_pil_image  # type: ignore

        if not self.model_id.strip():
            raise RuntimeError("RMBG 2.0 model_id is required")
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL.Image.Image")
        if not hasattr(fallback_mask, "size"):
            raise TypeError("fallback_mask must be a PIL.Image.Image-compatible object")
        self._lazy_load()
        processor = self._image_processor
        model = self._model
        if processor is None or model is None:
            raise RuntimeError("RMBG 2.0 model initialization failed")
        inputs = processor(images=image, return_tensors="pt")
        pixel_values = inputs.get("pixel_values")
        if pixel_values is None:
            raise RuntimeError("RMBG 2.0 processor did not return pixel_values")
        model_param = next(model.parameters())
        pixel_values = pixel_values.to(
            device=model_param.device,
            dtype=model_param.dtype,
            non_blocking=model_param.device.type == "cuda",
        )
        with torch.inference_mode():
            outputs = model(pixel_values)
        alpha = self._normalize_alpha(self._extract_prediction(outputs))
        mask = to_pil_image(alpha).resize(image.size, Image.Resampling.LANCZOS).convert("L")
        if mask.getbbox() is None:
            return fallback_mask
        if int((np.asarray(mask, dtype=np.uint8) > 8).sum()) < 32:
            return fallback_mask
        return mask
