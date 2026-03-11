from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .image_patch_ops import load_image_rgb
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
    validate_diffusers_runtime,
)

logger = get_logger("discoverex.models.sdxl_final")


class SdxlFinalRenderModel:
    def __init__(
        self,
        model_id: str = "stabilityai/sdxl-turbo",
        revision: str = "main",
        device: str = "cuda",
        dtype: str = "float16",
        precision: str = "fp16",
        batch_size: int = 1,
        seed: int | None = None,
        strict_runtime: bool = False,
        default_prompt: str = "polished hidden object puzzle final render",
        default_negative_prompt: str = "blurry, low quality, artifact",
        default_num_inference_steps: int = 20,
        default_guidance_scale: float = 5.0,
        default_strength: float = 0.25,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.dtype = dtype
        self.precision = precision
        self.batch_size = batch_size
        self.seed = seed
        self.strict_runtime = strict_runtime
        self.default_prompt = default_prompt
        self.default_negative_prompt = default_negative_prompt
        self.default_num_inference_steps = default_num_inference_steps
        self.default_guidance_scale = default_guidance_scale
        self.default_strength = default_strength
        self._pipe: Any | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        logger.info(
            "loading final render model model_id=%s revision=%s requested_device=%s",
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
            name="final_render_model",
            version=model_ref_or_version,
            runtime="sdxl_img2img",
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
        image_ref = request.image_ref
        if image_ref is None:
            raise ValueError("FxRequest.image_ref is required for final render")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        source = Path(str(image_ref))
        if not source.exists():
            raise ValueError(f"final render source image does not exist: {source}")
        prompt = as_str(request.params.get("prompt"), fallback=self.default_prompt)
        negative_prompt = as_str(
            request.params.get("negative_prompt"),
            fallback=self.default_negative_prompt,
        )
        seed = as_int_or_none(request.params.get("seed"), fallback=self.seed)
        num_inference_steps = as_positive_int(
            request.params.get("num_inference_steps"),
            fallback=self.default_num_inference_steps,
        )
        guidance_scale = as_float(
            request.params.get("guidance_scale"),
            fallback=self.default_guidance_scale,
        )
        strength = as_float(
            request.params.get("strength"),
            fallback=self.default_strength,
        )
        image = load_image_rgb(source)
        rendered = self._generate_image(
            handle=handle,
            source_image=image,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            strength=strength,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered.save(path)
        logger.info(
            "final render image saved path=%s duration=%s",
            path,
            format_seconds(started),
        )
        return {"fx": request.mode or "final_render", "output_path": str(path)}

    def _load_pipe(self, handle: ModelHandle) -> Any:
        if self._pipe is not None:
            return self._pipe
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
        pipe = AutoPipelineForImage2Image.from_pretrained(  # type: ignore[no-untyped-call]
            self.model_id,
            revision=self.revision,
            torch_dtype=torch_dtype,
        )
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=False)
        self._pipe = pipe.to(handle.device)
        return self._pipe

    def _generate_image(
        self,
        *,
        handle: ModelHandle,
        source_image: Any,
        prompt: str,
        negative_prompt: str,
        seed: int | None,
        num_inference_steps: int,
        guidance_scale: float,
        strength: float,
    ) -> Any:
        try:
            import torch  # type: ignore
        except Exception as exc:
            raise RuntimeError("torch runtime unavailable") from exc
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        pipe = self._load_pipe(handle)
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=source_image,
            strength=strength,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        images = getattr(result, "images", None)
        if not images:
            raise RuntimeError("img2img pipeline returned no images")
        return images[0]
