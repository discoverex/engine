from __future__ import annotations

# mypy: ignore-errors
from typing import Any

from ...pipeline_memory import configure_diffusers_pipeline


def load_pipeline(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    from diffusers import StableDiffusionXLPipeline  # type: ignore
    from huggingface_hub import hf_hub_download  # type: ignore
    from safetensors.torch import load_file  # type: ignore
    from .rootonchair_vae import TransparentVAEDecoder

    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    transparent_vae = TransparentVAEDecoder.from_pretrained(
        "madebyollin/sdxl-vae-fp16-fix",
        torch_dtype=torch_dtype,
    )
    transparent_vae.config.force_upcast = False
    decoder_path = hf_hub_download(
        repo_id="LayerDiffusion/layerdiffusion-v1",
        filename="vae_transparent_decoder.safetensors",
        cache_dir=model.weights_cache_dir,
    )
    transparent_vae.set_transparent_decoder(load_file(decoder_path))
    pipe = StableDiffusionXLPipeline.from_pretrained(
        model.model_id,
        vae=transparent_vae,
        revision=model.revision,
        torch_dtype=torch_dtype,
        variant="fp16" if "16" in handle.dtype else None,
        use_safetensors=True,
        add_watermarker=False,
    )
    if not model._layerdiffuse_applied:
        pipe.load_lora_weights(
            "rootonchair/diffuser_layerdiffuse",
            weight_name="diffuser_layer_xl_transparent_attn.safetensors",
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
    _ = (model, handle)
    return None
