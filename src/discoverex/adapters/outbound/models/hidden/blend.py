from __future__ import annotations

from typing import Any

from ..pipeline_memory import configure_diffusers_pipeline
from ..runtime import normalize_dtype, resolve_runtime, validate_diffusers_runtime
from .runtime import BackendRuntime, RuntimeHandle


class DiffusionObjectBlendBackend:
    def __init__(self, *, backend_name: str, model_id: str, runtime: BackendRuntime) -> None:
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
        import torch  # type: ignore
        from diffusers import AutoPipelineForInpainting  # type: ignore

        if not self.model_id.strip():
            raise RuntimeError(f"{self.backend_name} model_id is required")
        validate_diffusers_runtime(resolve_runtime())
        if self._pipe is None:
            pipe = AutoPipelineForInpainting.from_pretrained(self.model_id, dtype=normalize_dtype(self.runtime.dtype, torch))  # type: ignore[no-untyped-call]
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
        return self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image,
            mask_image=mask,
            strength=max(0.01, min(0.99, float(strength))),
            num_inference_steps=max(1, int(num_inference_steps)),
            guidance_scale=float(guidance_scale),
        ).images[0]
