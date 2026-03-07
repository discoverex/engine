from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.models.types import InpaintPrediction, InpaintRequest, ModelHandle

from .image_patch_ops import (
    apply_patch,
    crop_bbox,
    load_image_rgb,
    sanitize_bbox,
    save_image,
)
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
)


class HFInpaintModel:
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
        quality_model_id: str = "google/vit-base-patch16-224",
        generation_model_id: str = "hf-internal-testing/tiny-stable-diffusion-pipe",
        inpaint_mode: str = "fast_patch",
        generation_strength: float = 0.45,
        generation_steps: int = 6,
        generation_guidance_scale: float = 2.5,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.dtype = dtype
        self.precision = precision
        self.batch_size = batch_size
        self.seed = seed
        self.strict_runtime = strict_runtime
        self.quality_model_id = quality_model_id
        self.generation_model_id = generation_model_id
        self.inpaint_mode = inpaint_mode
        self.generation_strength = generation_strength
        self.generation_steps = generation_steps
        self.generation_guidance_scale = generation_guidance_scale
        self._quality_classifier: Any | None = None
        self._img2img_pipe: Any | None = None

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
            name="inpaint_model",
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
        self, handle: ModelHandle, request: InpaintRequest
    ) -> InpaintPrediction:
        result: InpaintPrediction = {
            "region_id": request.region_id,
            "model_id": self.model_id,
            "inpaint_mode": self.inpaint_mode,
        }
        quality = self._predict_quality(handle, request)
        if quality is None:
            quality = 0.86 if request.prompt else 0.80
        result["quality_score"] = quality

        composited_ref = self._predict_patch_and_composite(handle, request)
        if composited_ref is not None:
            result["patch_image_ref"] = str(composited_ref["patch"])
            result["composited_image_ref"] = str(composited_ref["composited"])
        return result

    def _predict_patch_and_composite(
        self, handle: ModelHandle, request: InpaintRequest
    ) -> dict[str, Path] | None:
        if request.image_ref is None or request.bbox is None:
            return None
        source = Path(str(request.image_ref))
        if not source.exists():
            return None
        output_path = request.output_path
        if output_path is None:
            return None
        try:
            image = load_image_rgb(source)
            bbox = sanitize_bbox(request.bbox, image.width, image.height)
            patch = crop_bbox(image, bbox)
            generated_patch = self._generate_patch_with_diffusers(
                handle, request, patch
            )
            composited = apply_patch(image, generated_patch, bbox)
            patch_path = save_image(
                generated_patch, Path(output_path).with_suffix(".patch.png")
            )
            composited_path = save_image(composited, output_path)
            return {"patch": patch_path, "composited": composited_path}
        except Exception:
            return None

    def _generate_patch_with_diffusers(
        self, handle: ModelHandle, request: InpaintRequest, patch_image: Any
    ) -> Any:
        try:
            import torch  # type: ignore
            from diffusers import StableDiffusionImg2ImgPipeline  # type: ignore
        except Exception as exc:
            raise RuntimeError("diffusers runtime unavailable") from exc

        if self._img2img_pipe is None:
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                self.generation_model_id,
                revision=self.revision,
                torch_dtype=torch.float32 if "32" in handle.dtype else torch.float16,
                safety_checker=None,
                feature_extractor=None,
                requires_safety_checker=False,
            )
            self._img2img_pipe = pipe.to(handle.device)
        prompt = (
            request.generation_prompt or request.prompt or "repair hidden object area"
        )
        result = self._img2img_pipe(
            prompt=prompt,
            image=patch_image,
            strength=float(request.generation_strength or self.generation_strength),
            num_inference_steps=int(request.generation_steps or self.generation_steps),
            guidance_scale=float(
                request.generation_guidance_scale or self.generation_guidance_scale
            ),
        )
        images = getattr(result, "images", None)
        if not images:
            raise RuntimeError("img2img returned no images")
        return images[0]

    def _predict_quality(
        self, handle: ModelHandle, request: InpaintRequest
    ) -> float | None:
        if not bool(handle.extra.get("runtime_available")):
            return None
        image_ref = request.image_ref
        if image_ref is None or request.bbox is None:
            return None
        image_path = Path(str(image_ref))
        if not image_path.exists():
            return None
        runtime = resolve_runtime()
        if not runtime.available or runtime.transformers is None:
            return None
        transformers = runtime.transformers
        try:
            if self._quality_classifier is None:
                device_arg = 0 if handle.device.startswith("cuda") else -1
                self._quality_classifier = transformers.pipeline(
                    "image-classification",
                    model=self.quality_model_id,
                    revision=self.revision,
                    device=device_arg,
                )
            image = load_image_rgb(image_path)
            box = sanitize_bbox(request.bbox, image.width, image.height)
            crop = crop_bbox(image, box)
            preds = self._quality_classifier(crop, top_k=1)
        except Exception:
            return None
        if not preds:
            return None
        score = preds[0].get("score")
        if isinstance(score, float):
            return max(0.0, min(1.0, score))
        return None
