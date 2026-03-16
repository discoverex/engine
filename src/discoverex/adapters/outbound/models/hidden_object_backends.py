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
            try:
                self._image_processor = AutoImageProcessor.from_pretrained(self.model_id)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load RMBG 2.0 image processor: {self.model_id}"
                ) from exc

        if self._model is None:
            device_str = str(self.runtime.device)
            if device_str.startswith("cpu"):
                torch_dtype = torch.float32
            else:
                torch_dtype = normalize_dtype(self.runtime.dtype, torch)

            try:
                model = AutoModelForImageSegmentation.from_pretrained(
                    self.model_id,
                    trust_remote_code=True,
                    torch_dtype=torch_dtype,
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to load RMBG 2.0 model: {self.model_id}") from exc

            try:
                model = model.to(self.runtime.device)
                if device_str.startswith("cpu"):
                    model = model.float()
                model.eval()
            except Exception as exc:
                raise RuntimeError("Failed to move RMBG 2.0 model to target device") from exc

            self._model = model

    def _extract_prediction(self, outputs: Any) -> Any:
        pred = getattr(outputs, "predicted_alpha", None)
        if pred is not None:
            return pred

        pred = getattr(outputs, "logits", None)
        if pred is not None:
            return pred

        if isinstance(outputs, (tuple, list)) and len(outputs) > 0:
            return outputs[0]

        if hasattr(outputs, "preds"):
            pred = getattr(outputs, "preds")
            if pred is not None:
                return pred

        raise RuntimeError("RMBG 2.0 returned no usable alpha prediction")

    def _normalize_alpha(self, pred: Any) -> Any:
        import torch  # type: ignore

        if not isinstance(pred, torch.Tensor):
            raise RuntimeError("RMBG 2.0 prediction is not a tensor")

        if pred.ndim == 4:
            # expected: [B, C, H, W]
            alpha = pred[0]
            if alpha.shape[0] == 1:
                alpha = alpha[0]
            else:
                alpha = alpha[0]
        elif pred.ndim == 3:
            # expected: [B, H, W] or [C, H, W]
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
        if not self.model_id.strip():
            raise RuntimeError("RMBG 2.0 model_id is required")

        try:
            import numpy as np  # type: ignore
            import torch  # type: ignore
            from PIL import Image  # type: ignore
            from torchvision.transforms.functional import to_pil_image  # type: ignore
        except Exception as exc:
            raise RuntimeError("RMBG 2.0 runtime unavailable") from exc

        validate_diffusers_runtime(self.runtime)

        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL.Image.Image")

        if not hasattr(fallback_mask, "size"):
            raise TypeError("fallback_mask must be a PIL.Image.Image-compatible object")

        self._lazy_load()

        processor = self._image_processor
        model = self._model

        if processor is None or model is None:
            raise RuntimeError("RMBG 2.0 model initialization failed")

        try:
            inputs = processor(images=image, return_tensors="pt")
        except Exception as exc:
            raise RuntimeError("RMBG 2.0 preprocessing failed") from exc

        pixel_values = inputs.get("pixel_values")
        if pixel_values is None:
            raise RuntimeError("RMBG 2.0 processor did not return pixel_values")

        try:
            model_param = next(model.parameters())
        except StopIteration as exc:
            raise RuntimeError("RMBG 2.0 model has no parameters") from exc

        model_device = model_param.device
        model_dtype = model_param.dtype

        try:
            pixel_values = pixel_values.to(
                device=model_device,
                dtype=model_dtype,
                non_blocking=model_device.type == "cuda",
            )
        except Exception as exc:
            raise RuntimeError("Failed to move RMBG 2.0 inputs to model device") from exc

        try:
            with torch.inference_mode():
                outputs = model(pixel_values)
        except Exception as exc:
            raise RuntimeError("RMBG 2.0 inference failed") from exc

        pred = self._extract_prediction(outputs)
        alpha = self._normalize_alpha(pred)

        try:
            mask = to_pil_image(alpha)
            mask = mask.resize(image.size, Image.LANCZOS).convert("L")
        except Exception as exc:
            raise RuntimeError("RMBG 2.0 postprocessing failed") from exc

        if mask.getbbox() is None:
            return fallback_mask

        mask_np = np.asarray(mask, dtype=np.uint8)
        positive_area = int((mask_np > 8).sum())
        if positive_area < 32:
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
