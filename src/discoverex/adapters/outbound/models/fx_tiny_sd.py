from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
)


class TinySDFxModel:
    def __init__(
        self,
        model_id: str = "hf-internal-testing/tiny-stable-diffusion-pipe",
        revision: str = "main",
        device: str = "cpu",
        dtype: str = "float32",
        precision: str = "fp32",
        batch_size: int = 1,
        seed: int | None = 7,
        strict_runtime: bool = True,
        default_prompt: str = "hidden object puzzle scene",
        default_negative_prompt: str = "blurry, low quality, artifact",
        default_num_inference_steps: int = 8,
        default_guidance_scale: float = 3.0,
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
        self._pipe: Any | None = None

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
            name="fx_model",
            version=model_ref_or_version,
            runtime="tiny_sd",
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
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")

        width = as_positive_int(request.params.get("width"), fallback=320)
        height = as_positive_int(request.params.get("height"), fallback=240)
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

        image = self._generate_image(
            handle=handle,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return {"fx": request.mode or "tiny_sd", "output_path": str(path)}

    def _load_pipe(self, handle: ModelHandle) -> Any:
        if self._pipe is not None:
            return self._pipe

        try:
            import torch  # type: ignore
            from diffusers import StableDiffusionPipeline  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "diffusers runtime unavailable. Install with ml-cpu extra."
            ) from exc

        normalized_dtype = handle.dtype.lower()
        torch_dtype = torch.float32 if "32" in normalized_dtype else torch.float16
        pipe = StableDiffusionPipeline.from_pretrained(  # type: ignore[no-untyped-call]
            self.model_id,
            revision=self.revision,
            torch_dtype=torch_dtype,
            safety_checker=None,
            feature_extractor=None,
            requires_safety_checker=False,
        )
        self._pipe = pipe.to(handle.device)
        return self._pipe

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
    ) -> Any:
        try:
            import torch  # type: ignore
        except Exception as exc:
            raise RuntimeError("torch runtime unavailable") from exc

        pipe = self._load_pipe(handle)
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        result = pipe(
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
            raise RuntimeError("stable diffusion pipeline returned no images")
        return images[0]
