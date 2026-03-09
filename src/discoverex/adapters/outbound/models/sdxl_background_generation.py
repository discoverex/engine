from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
    validate_diffusers_runtime,
)

logger = get_logger("discoverex.models.sdxl_background")


class SdxlBackgroundGenerationModel:
    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        revision: str = "main",
        device: str = "cuda",
        dtype: str = "float16",
        precision: str = "fp16",
        batch_size: int = 1,
        seed: int | None = None,
        strict_runtime: bool = False,
        refiner_model_id: str | None = "stabilityai/stable-diffusion-xl-refiner-1.0",
        default_prompt: str = "cinematic hidden object puzzle background",
        default_negative_prompt: str = "blurry, low quality, artifact",
        default_num_inference_steps: int = 30,
        default_guidance_scale: float = 7.5,
        default_refiner_strength: float = 0.2,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.dtype = dtype
        self.precision = precision
        self.batch_size = batch_size
        self.seed = seed
        self.strict_runtime = strict_runtime
        self.refiner_model_id = refiner_model_id
        self.default_prompt = default_prompt
        self.default_negative_prompt = default_negative_prompt
        self.default_num_inference_steps = default_num_inference_steps
        self.default_guidance_scale = default_guidance_scale
        self.default_refiner_strength = default_refiner_strength
        self._base_pipe: Any | None = None
        self._refiner_pipe: Any | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        logger.info(
            "loading background generation model model_id=%s revision=%s requested_device=%s",
            self.model_id,
            self.revision,
            self.device,
        )
        runtime = resolve_runtime()
        validate_diffusers_runtime(runtime)
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
            name="background_generation_model",
            version=model_ref_or_version,
            runtime="sdxl_text2image",
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

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        started = perf_counter()
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        width = as_positive_int(request.params.get("width"), fallback=1024)
        height = as_positive_int(request.params.get("height"), fallback=768)
        seed = as_int_or_none(request.params.get("seed"), fallback=self.seed)
        prompt = as_str(request.params.get("prompt"), fallback=self.default_prompt)
        negative_prompt = as_str(
            request.params.get("negative_prompt"),
            fallback=self.default_negative_prompt,
        )
        num_inference_steps = as_positive_int(
            request.params.get("num_inference_steps"),
            fallback=self.default_num_inference_steps,
        )
        guidance_scale = as_float(
            request.params.get("guidance_scale"),
            fallback=self.default_guidance_scale,
        )
        refiner_strength = as_float(
            request.params.get("refiner_strength"),
            fallback=self.default_refiner_strength,
        )
        image = self._generate_image(
            handle=handle,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            refiner_strength=refiner_strength,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        logger.info(
            "background generation image saved path=%s duration=%s",
            path,
            format_seconds(started),
        )
        return {"fx": request.mode or "background_generation", "output_path": str(path)}

    def _load_base_pipe(self, handle: ModelHandle) -> Any:
        if self._base_pipe is not None:
            return self._base_pipe
        try:
            import torch  # type: ignore
            from diffusers import AutoPipelineForText2Image  # type: ignore
        except Exception as exc:
            runtime = resolve_runtime()
            validate_diffusers_runtime(runtime)
            raise RuntimeError(
                "diffusers text-to-image pipeline import failed. "
                "Install compatible ml-gpu or ml-cpu dependencies."
            ) from exc
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        pipe = AutoPipelineForText2Image.from_pretrained(
            self.model_id,
            revision=self.revision,
            torch_dtype=torch_dtype,
        )
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=False)
        self._base_pipe = pipe.to(handle.device)
        return self._base_pipe

    def _load_refiner_pipe(self, handle: ModelHandle) -> Any | None:
        if not self.refiner_model_id:
            return None
        if self._refiner_pipe is not None:
            return self._refiner_pipe
        try:
            import torch  # type: ignore
            from diffusers import AutoPipelineForImage2Image  # type: ignore
        except Exception as exc:
            runtime = resolve_runtime()
            validate_diffusers_runtime(runtime)
            raise RuntimeError(
                "diffusers image-to-image pipeline import failed. "
                "Install compatible ml-gpu or ml-cpu dependencies."
            ) from exc
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        pipe = AutoPipelineForImage2Image.from_pretrained(
            self.refiner_model_id,
            torch_dtype=torch_dtype,
        )
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=False)
        self._refiner_pipe = pipe.to(handle.device)
        return self._refiner_pipe

    def _generate_image(
        self,
        *,
        handle: ModelHandle,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int | None,
        num_inference_steps: int,
        guidance_scale: float,
        refiner_strength: float,
    ) -> Any:
        try:
            import torch  # type: ignore
        except Exception as exc:
            raise RuntimeError("torch runtime unavailable") from exc
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        base_pipe = self._load_base_pipe(handle)
        result = base_pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator,
        )
        images = getattr(result, "images", None)
        if not images:
            raise RuntimeError("text2image pipeline returned no images")
        image = images[0]
        refiner = self._load_refiner_pipe(handle)
        if refiner is None:
            return image
        refined = refiner(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image,
            strength=refiner_strength,
            num_inference_steps=max(10, num_inference_steps // 2),
            guidance_scale=guidance_scale,
            generator=generator,
        )
        refined_images = getattr(refined, "images", None)
        if not refined_images:
            return image
        return refined_images[0]
