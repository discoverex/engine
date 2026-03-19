from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.models.types import ModelHandle, PerceptionRequest

from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
)
from .runtime_cleanup import clear_model_runtime


class HFPerceptionModel:
    def __init__(
        self,
        model_id: str,
        revision: str = "main",
        device: str = "cuda",
        dtype: str = "float16",
        precision: str = "fp16",
        batch_size: int = 1,
        seed: int | None = None,
        strict_runtime: bool = False,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.dtype = dtype
        self.precision = precision
        self.batch_size = batch_size
        self.seed = seed
        self.strict_runtime = strict_runtime
        self._image_processor: Any | None = None
        self._model: Any | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        runtime = resolve_runtime()
        selected_device = resolve_device(self.device, runtime.torch)
        selected_dtype = str(normalize_dtype(self.dtype, runtime.torch))
        if self.strict_runtime and not runtime.available:
            raise RuntimeError(
                f"torch/transformers runtime unavailable: {runtime.reason}"
            )
        if self.strict_runtime and selected_device != self.device:
            raise RuntimeError(f"requested device '{self.device}' is unavailable")
        apply_seed(self.seed, runtime.torch)
        return ModelHandle(
            name="perception_model",
            version=model_ref_or_version,
            runtime="hf",
            model_id=self.model_id,
            revision=self.revision,
            device=selected_device,
            dtype=selected_dtype,
            extra=build_runtime_extra(
                runtime=runtime,
                requested_device=self.device,
                selected_device=selected_device,
                requested_dtype=self.dtype,
                selected_dtype=selected_dtype,
                precision=self.precision,
                batch_size=self.batch_size,
                seed=self.seed,
            ),
        )

    def predict(
        self, handle: ModelHandle, request: PerceptionRequest
    ) -> dict[str, float]:
        confidence = self._predict_with_transformers_if_available(handle, request)
        if confidence is None:
            confidence = self._predict_fallback(request)
        return {"confidence": confidence}

    def _predict_with_transformers_if_available(
        self,
        handle: ModelHandle,
        request: PerceptionRequest,
    ) -> float | None:
        if not bool(handle.extra.get("runtime_available")):
            return None
        image_ref = request.image_ref
        if image_ref is None:
            return None
        image_path = Path(image_ref)
        if not image_path.exists():
            return None
        try:
            from PIL import Image
        except Exception:
            return None

        runtime = resolve_runtime()
        if not runtime.available or runtime.transformers is None:
            return None
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                AutoModelForImageClassification,
                ViTImageProcessor,
            )

            if self._model is None:
                self._image_processor = ViTImageProcessor.from_pretrained(
                    self.model_id,
                    revision=self.revision,
                )
                self._model = AutoModelForImageClassification.from_pretrained(
                    self.model_id,
                    revision=self.revision,
                )
                if handle.device:
                    self._model = self._model.to(handle.device)
            image = Image.open(image_path).convert("RGB")
            processor = self._image_processor
            model = self._model
            if processor is None or model is None:
                return None
            inputs = processor(images=image, return_tensors="pt")
            if handle.device:
                inputs = {
                    key: value.to(handle.device) if hasattr(value, "to") else value
                    for key, value in inputs.items()
                }
            with torch.no_grad():
                outputs = model(**inputs)
            logits = getattr(outputs, "logits", None)
            if logits is None:
                return None
            score = float(torch.nn.functional.softmax(logits, dim=-1).max().item())
        except Exception:
            return None

        return max(0.0, min(1.0, score))

    def unload(self) -> None:
        clear_model_runtime(self._image_processor, self._model)
        self._image_processor = None
        self._model = None

    def _predict_fallback(self, request: PerceptionRequest) -> float:
        region_factor = min(0.45, 0.08 * request.region_count)
        context_bonus = 0.05 if request.question_context else 0.0
        confidence = min(1.0, 0.5 + region_factor + context_bonus)
        return confidence
