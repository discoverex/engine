from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pipeline_memory import OffloadMode, configure_diffusers_pipeline
from .runtime import normalize_dtype, resolve_runtime, validate_diffusers_runtime


@dataclass(frozen=True)
class BackendRuntime:
    device: str
    dtype: str
    offload_mode: OffloadMode
    enable_attention_slicing: bool
    enable_vae_slicing: bool
    enable_vae_tiling: bool
    enable_xformers_memory_efficient_attention: bool
    enable_fp8_layerwise_casting: bool
    enable_channels_last: bool


class Rmbg20MaskRefiner:
    def __init__(
        self,
        *,
        model_id: str,
        runtime: BackendRuntime,
    ) -> None:
        self.model_id = model_id
        self.runtime = runtime
        self._model: Any | None = None
        self._image_processor: Any | None = None

    def refine(self, *, image: Any, fallback_mask: Any) -> Any:
        if not self.model_id.strip():
            raise RuntimeError("RMBG 2.0 model_id is required")
        try:
            import torch  # type: ignore
            from PIL import Image  # type: ignore
            from torchvision import transforms  # type: ignore
            from transformers import (  # type: ignore
                AutoImageProcessor,
                AutoModelForImageSegmentation,
            )
        except Exception as exc:
            raise RuntimeError("RMBG 2.0 runtime unavailable") from exc

        runtime = resolve_runtime()
        validate_diffusers_runtime(runtime)
        if self._image_processor is None:
            self._image_processor = AutoImageProcessor.from_pretrained(self.model_id)
        if self._model is None:
            torch_dtype = normalize_dtype(self.runtime.dtype, torch)
            self._model = AutoModelForImageSegmentation.from_pretrained(
                self.model_id,
                trust_remote_code=True,
                torch_dtype=torch_dtype,
            ).to(self.runtime.device)

        processor = self._image_processor
        model = self._model
        inputs = processor(images=image, return_tensors="pt")
        inputs = {
            key: value.to(self.runtime.device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
        with torch.no_grad():
            outputs = model(inputs["pixel_values"])
        pred = getattr(outputs, "predicted_alpha", None)
        if pred is None:
            pred = getattr(outputs, "logits", None)
        if pred is None:
            raise RuntimeError("RMBG 2.0 returned no alpha prediction")
        alpha = pred[0]
        if alpha.ndim == 3:
            alpha = alpha[0]
        alpha = alpha.detach().float().cpu().clamp(0, 1)
        to_pil = transforms.ToPILImage()
        mask = to_pil(alpha)
        mask = mask.resize(image.size, Image.LANCZOS).convert("L")
        if mask.getbbox() is None:
            return fallback_mask
        return mask


class Sam2MaskRefiner:
    def __init__(
        self,
        *,
        model_id: str,
        runtime: BackendRuntime,
    ) -> None:
        self.model_id = model_id
        self.runtime = runtime
        self._predictor: Any | None = None

    def refine(self, *, image: Any, fallback_mask: Any) -> Any:
        if not self.model_id.strip():
            raise RuntimeError("SAM2 model_id is required")
        try:
            import numpy as np
            from PIL import Image  # type: ignore
            from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore
        except Exception as exc:
            raise RuntimeError("SAM2 runtime unavailable") from exc

        if self._predictor is None:
            self._predictor = SAM2ImagePredictor.from_pretrained(self.model_id)

        predictor = self._predictor
        if predictor is None:
            raise RuntimeError("SAM2 predictor initialization failed")
        bbox = fallback_mask.getbbox()
        if bbox is None:
            return fallback_mask
        predictor.set_image(np.array(image.convert("RGB")))
        masks, scores, _ = predictor.predict(
            box=np.array([bbox], dtype=np.float32),
            multimask_output=True,
        )
        if len(masks) == 0:
            return fallback_mask
        best_index = max(range(len(scores)), key=lambda idx: float(scores[idx]))
        mask = Image.fromarray((masks[best_index].astype("uint8") * 255), mode="L")
        if mask.getbbox() is None:
            return fallback_mask
        return mask


class IcLightRelighter:
    def __init__(
        self,
        *,
        model_id: str,
        runtime: BackendRuntime,
    ) -> None:
        self.model_id = model_id
        self.runtime = runtime
        self._pipe: Any | None = None

    def relight(
        self,
        *,
        rgba_object: Any,
        prompt: str,
        negative_prompt: str,
        strength: float = 0.18,
    ) -> Any:
        if not self.model_id.strip():
            raise RuntimeError("IC-Light model_id is required")
        try:
            import torch  # type: ignore
            from diffusers import AutoPipelineForImage2Image  # type: ignore
            from PIL import Image  # type: ignore
        except Exception as exc:
            raise RuntimeError("IC-Light runtime unavailable") from exc

        runtime = resolve_runtime()
        validate_diffusers_runtime(runtime)
        if self._pipe is None:
            torch_dtype = normalize_dtype(self.runtime.dtype, torch)
            pipe = AutoPipelineForImage2Image.from_pretrained(
                self.model_id,
                torch_dtype=torch_dtype,
            )
            pipe = configure_diffusers_pipeline(
                pipe,
                handle=_RuntimeHandle(self.runtime),
                offload_mode=self.runtime.offload_mode,
                enable_attention_slicing=self.runtime.enable_attention_slicing,
                enable_vae_slicing=self.runtime.enable_vae_slicing,
                enable_vae_tiling=self.runtime.enable_vae_tiling,
                enable_xformers_memory_efficient_attention=self.runtime.enable_xformers_memory_efficient_attention,
                enable_fp8_layerwise_casting=self.runtime.enable_fp8_layerwise_casting,
                enable_channels_last=self.runtime.enable_channels_last,
            )
            self._pipe = pipe
        pipe = self._pipe
        background = Image.new("RGBA", rgba_object.size, color=(127, 127, 127, 255))
        flat = Image.alpha_composite(background, rgba_object.convert("RGBA")).convert("RGB")
        relit = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=flat,
            strength=max(0.01, min(0.99, float(strength))),
        ).images[0]
        relit_rgba = relit.convert("RGBA")
        relit_rgba.putalpha(rgba_object.getchannel("A"))
        return relit_rgba


class DiffusionObjectBlendBackend:
    def __init__(
        self,
        *,
        backend_name: str,
        model_id: str,
        runtime: BackendRuntime,
    ) -> None:
        self.backend_name = backend_name
        self.model_id = model_id
        self.runtime = runtime
        self._pipe: Any | None = None

    def generate(
        self,
        *,
        image: Any,
        mask: Any,
        prompt: str,
        negative_prompt: str,
        strength: float,
        num_inference_steps: int,
        guidance_scale: float,
    ) -> Any:
        if not self.model_id.strip():
            raise RuntimeError(f"{self.backend_name} model_id is required")
        try:
            import torch  # type: ignore
            from diffusers import AutoPipelineForInpainting  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"{self.backend_name} runtime unavailable") from exc

        runtime = resolve_runtime()
        validate_diffusers_runtime(runtime)
        if self._pipe is None:
            torch_dtype = normalize_dtype(self.runtime.dtype, torch)
            pipe = AutoPipelineForInpainting.from_pretrained(
                self.model_id,
                torch_dtype=torch_dtype,
            )
            pipe = configure_diffusers_pipeline(
                pipe,
                handle=_RuntimeHandle(self.runtime),
                offload_mode=self.runtime.offload_mode,
                enable_attention_slicing=self.runtime.enable_attention_slicing,
                enable_vae_slicing=self.runtime.enable_vae_slicing,
                enable_vae_tiling=self.runtime.enable_vae_tiling,
                enable_xformers_memory_efficient_attention=self.runtime.enable_xformers_memory_efficient_attention,
                enable_fp8_layerwise_casting=self.runtime.enable_fp8_layerwise_casting,
                enable_channels_last=self.runtime.enable_channels_last,
            )
            self._pipe = pipe
        return self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image,
            mask_image=mask,
            strength=max(0.01, min(0.99, float(strength))),
            num_inference_steps=max(1, int(num_inference_steps)),
            guidance_scale=float(guidance_scale),
        ).images[0]


@dataclass(frozen=True)
class _RuntimeHandle:
    runtime: BackendRuntime

    @property
    def device(self) -> str:
        return self.runtime.device

    @property
    def dtype(self) -> str:
        return self.runtime.dtype
