from __future__ import annotations

from pathlib import Path

from discoverex.models.types import ModelHandle, PerceptionRequest

from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
)


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
        self._pipeline: object | None = None

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
        transformers = runtime.transformers

        try:
            if self._pipeline is None:
                device_arg = 0 if handle.device.startswith("cuda") else -1
                self._pipeline = transformers.pipeline(
                    "image-classification",
                    model=self.model_id,
                    revision=self.revision,
                    device=device_arg,
                    local_files_only=True,
                )
            image = Image.open(image_path).convert("RGB")
            pipeline = self._pipeline
            if not callable(pipeline):
                return None
            preds = pipeline(image, top_k=1)
        except Exception:
            return None

        if not preds:
            return None
        top = preds[0]
        score = top.get("score")
        if isinstance(score, float):
            return max(0.0, min(1.0, score))
        return None

    def _predict_fallback(self, request: PerceptionRequest) -> float:
        region_factor = min(0.45, 0.08 * request.region_count)
        context_bonus = 0.05 if request.question_context else 0.0
        confidence = min(1.0, 0.5 + region_factor + context_bonus)
        return confidence
