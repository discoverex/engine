from __future__ import annotations

import logging
from typing import Any

from ..pipeline_memory import configure_diffusers_pipeline
from ..runtime import normalize_dtype
from .runtime import BackendRuntime, RuntimeHandle


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
        self._logger.warning(message if exc is None else "%s: %s", message, exc)

    def _load_pipe(self) -> Any | None:
        try:
            import torch  # type: ignore
            from diffusers import AutoPipelineForImage2Image  # type: ignore
        except Exception as exc:
            self._raise_or_log("IC-Light runtime unavailable", exc=exc)
            return None
        if not self.base_model_id:
            self._raise_or_log("IC-Light relighter requires `base_model_id`. Returning original image.")
            return None
        if self._pipe is None:
            torch_dtype = torch.float32 if str(self.runtime.device).startswith("cpu") else normalize_dtype(self.runtime.dtype, torch)
            pipe = AutoPipelineForImage2Image.from_pretrained(self.base_model_id, dtype=torch_dtype)  # type: ignore[no-untyped-call]
            self._pipe = configure_diffusers_pipeline(
                pipe,
                handle=RuntimeHandle(self.runtime),
                offload_mode=self.runtime.offload_mode,
                enable_attention_slicing=self.runtime.enable_attention_slicing,
                enable_vae_slicing=self.runtime.enable_vae_slicing,
                enable_vae_tiling=self.runtime.enable_vae_tiling,
                enable_xformers_memory_efficient_attention=self.runtime.enable_xformers_memory_efficient_attention,
                enable_fp8_layerwise_casting=self.runtime.enable_fp8_layerwise_casting,
                enable_channels_last=self.runtime.enable_channels_last,
            )
            if self.model_id and self.model_id != self.base_model_id:
                self._raise_or_log("IC-Light weights injection is not implemented yet. Using the base img2img pipeline without IC-Light weights.")
        return self._pipe

    def relight(self, *, rgba_object: Any, prompt: str, negative_prompt: str, strength: float = 0.18, num_inference_steps: int = 20, guidance_scale: float = 5.0, seed: int | None = None) -> Any:
        import torch  # type: ignore
        from PIL import Image  # type: ignore

        if not isinstance(rgba_object, Image.Image):
            self._raise_or_log("rgba_object must be a PIL.Image.Image")
            return rgba_object
        rgba = rgba_object.convert("RGBA")
        pipe = self._load_pipe()
        if pipe is None:
            return rgba
        generator = None
        if seed is not None:
            try:
                generator = torch.Generator(device="cuda" if str(self.runtime.device).startswith("cuda") else "cpu").manual_seed(int(seed))
            except Exception as exc:
                self._raise_or_log("Failed to create deterministic generator for relight", exc=exc)
        flat = Image.alpha_composite(Image.new("RGBA", rgba.size, color=self.flat_background_rgba), rgba).convert("RGB")
        try:
            with torch.inference_mode():
                result = pipe(
                    prompt=prompt or "",
                    negative_prompt=negative_prompt or "",
                    image=flat,
                    strength=max(0.01, min(0.99, float(strength))),
                    num_inference_steps=max(1, int(num_inference_steps)),
                    guidance_scale=float(guidance_scale),
                    generator=generator,
                )
        except Exception as exc:
            self._raise_or_log("IC-Light relight inference failed", exc=exc)
            return rgba
        images = getattr(result, "images", None)
        if not images:
            self._raise_or_log("IC-Light relight pipeline returned no images")
            return rgba
        relit_rgba = images[0].convert("RGBA")
        if relit_rgba.size != rgba.size:
            relit_rgba = relit_rgba.resize(rgba.size, Image.Resampling.LANCZOS)
        relit_rgba.putalpha(rgba.getchannel("A").resize(relit_rgba.size))
        return relit_rgba

    def clear(self) -> None:
        self._pipe = None
