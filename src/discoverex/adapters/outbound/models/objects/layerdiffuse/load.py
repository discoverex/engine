from __future__ import annotations

# mypy: ignore-errors
import importlib
from typing import Any

from ...model_loading import load_state_dict_materialized
from ...pipeline_memory import configure_diffusers_pipeline
from .cache import ATTN_OFFSET_URL, TRANSPARENT_DECODER_URL, download_weight


def load_pipeline(*, model: Any, handle: Any) -> Any:
    import safetensors.torch as sf  # type: ignore
    import torch  # type: ignore
    from diffusers import (  # type: ignore
        AutoPipelineForText2Image,
        DPMSolverMultistepScheduler,
    )

    pipe = AutoPipelineForText2Image.from_pretrained(
        model.model_id,
        revision=model.revision,
        dtype=torch.float32 if "32" in handle.dtype else torch.float16,
        variant="fp16" if "16" in handle.dtype else None,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True, algorithm_type="dpmsolver++", solver_order=2)
    attn_path = download_weight(cache_dir=model.weights_cache_dir, url=ATTN_OFFSET_URL, filename="ld_diffusers_sdxl_attn.safetensors")
    if not model._layerdiffuse_applied:
        offset = sf.load_file(str(attn_path))
        base_state = pipe.unet.state_dict()
        load_state_dict_materialized(
            pipe.unet,
            {key: base_state[key] + offset[key] if key in offset else base_state[key] for key in base_state},
            strict=True,
        )
        model._layerdiffuse_applied = True
    return configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode=model.offload_mode,
        enable_attention_slicing=model.enable_attention_slicing,
        enable_vae_slicing=model.enable_vae_slicing,
        enable_vae_tiling=model.enable_vae_tiling,
        enable_xformers_memory_efficient_attention=model.enable_xformers_memory_efficient_attention,
        enable_fp8_layerwise_casting=model.enable_fp8_layerwise_casting,
        enable_channels_last=model.enable_channels_last,
    )


def load_transparent_decoder(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore

    transparent_vae = importlib.import_module("discoverex.adapters.outbound.models.layerdiffuse_transparent_vae")
    decoder_path = download_weight(
        cache_dir=model.weights_cache_dir,
        url=TRANSPARENT_DECODER_URL,
        filename="ld_diffusers_sdxl_vae_transparent_decoder.safetensors",
    )
    return transparent_vae.TransparentVAEDecoder(
        str(decoder_path),
        dtype=torch.float32 if "32" in handle.dtype else torch.float16,
    )
