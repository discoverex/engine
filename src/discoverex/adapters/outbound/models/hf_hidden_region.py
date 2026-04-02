from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.models.types import HiddenRegionRequest, ModelHandle
from discoverex.runtime_logging import get_logger

from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
)
from .runtime_cleanup import clear_model_runtime

logger = get_logger("discoverex.models.hidden_region")


class HFHiddenRegionModel:
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
        self._detector: Any | None = None

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
            name="hidden_region_model",
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
        self, handle: ModelHandle, request: HiddenRegionRequest
    ) -> list[tuple[float, float, float, float]]:
        detected = self._predict_with_transformers_if_available(handle, request)
        if detected:
            return detected
        width = max(1, request.width)
        height = max(1, request.height)
        # Fallback deterministic layout for non-path inputs like bg://dummy.
        return [
            (0.12 * width, 0.18 * height, 0.16 * width, 0.20 * height),
            (0.44 * width, 0.42 * height, 0.17 * width, 0.19 * height),
            (0.70 * width, 0.28 * height, 0.13 * width, 0.14 * height),
        ]

    def _predict_with_transformers_if_available(
        self,
        handle: ModelHandle,
        request: HiddenRegionRequest,
    ) -> list[tuple[float, float, float, float]] | None:
        if not bool(handle.extra.get("runtime_available")):
            logger.warning(
                "hidden_region transformers path skipped: runtime unavailable reason=%s",
                handle.extra.get("runtime_reason", ""),
            )
            return None
        image_ref = request.image_ref
        if image_ref is None:
            logger.warning(
                "hidden_region transformers path skipped: image_ref is missing"
            )
            return None
        image_path = Path(image_ref)
        if not image_path.exists():
            logger.warning(
                "hidden_region transformers path skipped: image path does not exist path=%s",
                image_path,
            )
            return None
        try:
            from PIL import Image
        except Exception as exc:
            logger.warning(
                "hidden_region transformers path skipped: failed to import PIL error=%s",
                exc,
            )
            return None

        runtime = resolve_runtime()
        if not runtime.available or runtime.transformers is None:
            logger.warning(
                "hidden_region transformers path skipped after runtime resolve: available=%s reason=%s",
                runtime.available,
                runtime.reason,
            )
            return None
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                AutoImageProcessor,
                AutoModelForObjectDetection,
            )
        except Exception as exc:
            logger.warning(
                "hidden_region transformers import failed model_id=%s revision=%s error=%s",
                self.model_id,
                self.revision,
                exc,
            )
            return None

        try:
            if self._detector is None:
                logger.info(
                    "loading hidden_region detector model_id=%s revision=%s device=%s",
                    self.model_id,
                    self.revision,
                    handle.device,
                )
                self._image_processor = AutoImageProcessor.from_pretrained(  # type: ignore[no-untyped-call]
                    self.model_id,
                    revision=self.revision,
                    use_fast=True,
                )
                self._detector = AutoModelForObjectDetection.from_pretrained(  # type: ignore[no-untyped-call]
                    self.model_id,
                    revision=self.revision,
                    low_cpu_mem_usage=False,
                )
                if handle.device:
                    self._detector = self._detector.to(handle.device)
            detector = self._detector
            processor = self._image_processor
            if detector is None or processor is None:
                logger.warning(
                    "hidden_region detector unavailable after load model_id=%s",
                    self.model_id,
                )
                return None
            image = Image.open(image_path).convert("RGB")
            inputs = processor(images=image, return_tensors="pt")
            if handle.device:
                inputs = {
                    key: value.to(handle.device) if hasattr(value, "to") else value
                    for key, value in inputs.items()
                }
            with torch.no_grad():
                outputs = detector(**inputs)
            target_sizes = torch.tensor(
                [[image.height, image.width]],
                device=outputs.logits.device,
            )
            processed = processor.post_process_object_detection(
                outputs,
                threshold=0.2,
                target_sizes=target_sizes,
            )
            preds = processed[0] if processed else {}
        except Exception as exc:
            logger.exception(
                "hidden_region detector inference failed model_id=%s image=%s error=%s",
                self.model_id,
                image_path,
                exc,
            )
            return None

        if not isinstance(preds, dict):
            logger.warning(
                "hidden_region detector returned unexpected payload type=%s",
                type(preds).__name__,
            )
            return None
        width = max(1, request.width)
        height = max(1, request.height)
        boxes: list[tuple[float, float, float, float]] = []
        pred_boxes = preds.get("boxes")
        if pred_boxes is None:
            logger.warning(
                "hidden_region detector returned no boxes model_id=%s",
                self.model_id,
            )
            return None
        for box in pred_boxes[:3]:
            values = box.tolist() if hasattr(box, "tolist") else list(box)
            if len(values) != 4:
                continue
            xmin, ymin, xmax, ymax = [float(value) for value in values]
            x = max(0.0, min(xmin, float(width)))
            y = max(0.0, min(ymin, float(height)))
            w = max(1.0, min(xmax, float(width)) - x)
            h = max(1.0, min(ymax, float(height)) - y)
            boxes.append((x, y, w, h))
        logger.info("hidden_region detector produced %d candidate boxes", len(boxes))
        return boxes or None

    def unload(self) -> None:
        clear_model_runtime(self._image_processor, self._detector)
        self._image_processor = None
        self._detector = None
