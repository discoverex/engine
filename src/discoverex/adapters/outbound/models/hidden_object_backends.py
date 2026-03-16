from __future__ import annotations

import logging
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
        base_model_id: str | None = None,
        strict: bool = False,
        flat_background_rgba: tuple[int, int, int, int] = (127, 127, 127, 255),
    ) -> None:
        self.model_id = model_id.strip()
        self.runtime = runtime
        self.base_model_id = (base_model_id or "").strip()
        self.strict = strict
        self.flat_background_rgba = flat_background_rgba

        self._pipe: Any | None = None
        self._logger = logging.getLogger(__name__)

    def _raise_or_log(self, message: str, *, exc: Exception | None = None) -> None:
        if self.strict:
            if exc is None:
                raise RuntimeError(message)
            raise RuntimeError(message) from exc

        if exc is None:
            self._logger.warning(message)
        else:
            self._logger.warning("%s: %s", message, exc)

    def _validate_runtime(self) -> None:
        required_attrs = (
            "device",
            "dtype",
            "offload_mode",
            "enable_attention_slicing",
            "enable_vae_slicing",
            "enable_vae_tiling",
            "enable_xformers_memory_efficient_attention",
            "enable_fp8_layerwise_casting",
            "enable_channels_last",
        )
        for attr_name in required_attrs:
            if not hasattr(self.runtime, attr_name):
                raise RuntimeError(f"Backend runtime missing required field: {attr_name}")

    def _resolve_torch_dtype(self, torch: Any) -> Any:
        device_str = str(self.runtime.device)
        if device_str.startswith("cpu"):
            return torch.float32
        return normalize_dtype(self.runtime.dtype, torch)

    def _configure_pipe(self, pipe: Any) -> Any:
        return configure_diffusers_pipeline(
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

    def _maybe_attach_ic_light_weights(self, pipe: Any) -> Any:
        """
        Extension point.

        `self.base_model_id` should be a valid diffusers img2img pipeline repo.
        `self.model_id` is treated as an IC-Light weights source or config source.

        If you later implement actual IC-Light injection logic, do it here.
        Right now this method is intentionally a no-op unless model_id is empty
        or identical to base_model_id.
        """
        if not self.model_id:
            return pipe

        if self.model_id == self.base_model_id:
            return pipe

        self._raise_or_log(
            "IC-Light weights injection is not implemented yet. "
            "Using the base img2img pipeline without IC-Light weights."
        )
        return pipe

    def _load_pipe(self) -> Any | None:
        if self._pipe is not None:
            return self._pipe

        try:
            import torch  # type: ignore
            from diffusers import AutoPipelineForImage2Image  # type: ignore
        except Exception as exc:
            self._raise_or_log("IC-Light runtime unavailable", exc=exc)
            return None

        try:
            self._validate_runtime()
        except Exception as exc:
            self._raise_or_log("Invalid backend runtime for IC-Light relighter", exc=exc)
            return None

        if not self.base_model_id:
            self._raise_or_log(
                "IC-Light relighter requires `base_model_id` for a valid diffusers "
                "image-to-image pipeline. Returning original image."
            )
            return None

        torch_dtype = self._resolve_torch_dtype(torch)

        try:
            pipe = AutoPipelineForImage2Image.from_pretrained(
                self.base_model_id,
                torch_dtype=torch_dtype,
            )
        except Exception as exc:
            self._raise_or_log(
                f"Failed to load base img2img pipeline: {self.base_model_id}",
                exc=exc,
            )
            return None

        try:
            pipe = self._configure_pipe(pipe)
        except Exception as exc:
            self._raise_or_log(
                "Failed to configure base img2img pipeline for relighting",
                exc=exc,
            )
            return None

        try:
            pipe = self._maybe_attach_ic_light_weights(pipe)
        except Exception as exc:
            self._raise_or_log(
                "Failed while applying IC-Light customization to the base pipeline",
                exc=exc,
            )
            return None

        self._pipe = pipe
        return self._pipe

    def relight(
        self,
        *,
        rgba_object: Any,
        prompt: str,
        negative_prompt: str,
        strength: float = 0.18,
        num_inference_steps: int = 20,
        guidance_scale: float = 5.0,
        seed: int | None = None,
    ) -> Any:
        try:
            import torch  # type: ignore
            from PIL import Image  # type: ignore
        except Exception as exc:
            self._raise_or_log("IC-Light runtime unavailable during relight", exc=exc)
            return rgba_object

        if not isinstance(rgba_object, Image.Image):
            self._raise_or_log("rgba_object must be a PIL.Image.Image")
            return rgba_object

        rgba = rgba_object.convert("RGBA")
        pipe = self._load_pipe()
        if pipe is None:
            return rgba

        safe_strength = max(0.01, min(0.99, float(strength)))
        safe_steps = max(1, int(num_inference_steps))
        safe_guidance = float(guidance_scale)

        background = Image.new("RGBA", rgba.size, color=self.flat_background_rgba)
        flat = Image.alpha_composite(background, rgba).convert("RGB")

        generator = None
        if seed is not None:
            try:
                device_for_generator = "cuda" if str(self.runtime.device).startswith("cuda") else "cpu"
                generator = torch.Generator(device=device_for_generator).manual_seed(int(seed))
            except Exception as exc:
                self._raise_or_log("Failed to create deterministic generator for relight", exc=exc)
                generator = None

        kwargs: dict[str, Any] = {
            "prompt": prompt or "",
            "negative_prompt": negative_prompt or "",
            "image": flat,
            "strength": safe_strength,
            "num_inference_steps": safe_steps,
            "guidance_scale": safe_guidance,
        }
        if generator is not None:
            kwargs["generator"] = generator

        try:
            with torch.inference_mode():
                result = pipe(**kwargs)
        except Exception as exc:
            self._raise_or_log("IC-Light relight inference failed", exc=exc)
            return rgba

        images = getattr(result, "images", None)
        if not images:
            self._raise_or_log("IC-Light relight pipeline returned no images")
            return rgba

        relit = images[0]
        if not isinstance(relit, Image.Image):
            self._raise_or_log("IC-Light relight output is not a PIL image")
            return rgba

        try:
            relit_rgba = relit.convert("RGBA")
            relit_rgba.putalpha(rgba.getchannel("A"))
            return relit_rgba
        except Exception as exc:
            self._raise_or_log("Failed to rebuild RGBA output after relight", exc=exc)
            return rgba

    def clear(self) -> None:
        self._pipe = None

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
