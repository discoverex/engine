from __future__ import annotations

# mypy: ignore-errors
from typing import Any

from ...pipeline_memory import configure_diffusers_pipeline


def load_pipeline(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline  # type: ignore
    from huggingface_hub import hf_hub_download  # type: ignore
    from safetensors.torch import load_file  # type: ignore
    from .rootonchair_vae import TransparentVAEDecoder
    from .rootonchair_sd15.loaders import load_lora_to_unet

    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    is_sdxl = "xl" in str(model.model_id).lower() or "sdxl" in str(model.model_id).lower()
    if is_sdxl:
        transparent_vae = TransparentVAEDecoder.from_pretrained(
            "madebyollin/sdxl-vae-fp16-fix",
            torch_dtype=torch_dtype,
        )
        decoder_repo = "LayerDiffusion/layerdiffusion-v1"
        decoder_filename = "vae_transparent_decoder.safetensors"
        pipeline_cls = StableDiffusionXLPipeline
        pipeline_kwargs: dict[str, Any] = {
            "revision": model.revision,
            "torch_dtype": torch_dtype,
            "variant": "fp16" if "16" in handle.dtype else None,
            "use_safetensors": True,
            "add_watermarker": False,
        }
        lora_repo = "rootonchair/diffuser_layerdiffuse"
        lora_weight_name = "diffuser_layer_xl_transparent_attn.safetensors"
    else:
        transparent_vae = TransparentVAEDecoder.from_pretrained(
            model.model_id,
            subfolder="vae",
            torch_dtype=torch_dtype,
        )
        decoder_repo = "LayerDiffusion/layerdiffusion-v1"
        decoder_filename = "layer_sd15_vae_transparent_decoder.safetensors"
        pipeline_cls = StableDiffusionPipeline
        pipeline_kwargs = {
            "torch_dtype": torch_dtype,
            "safety_checker": None,
        }
        lora_repo = "LayerDiffusion/layerdiffusion-v1"
        lora_weight_name = "layer_sd15_transparent_attn.safetensors"
    transparent_vae.config.force_upcast = False
    decoder_path = hf_hub_download(
        repo_id=decoder_repo,
        filename=decoder_filename,
        cache_dir=model.weights_cache_dir,
    )
    transparent_vae.set_transparent_decoder(load_file(decoder_path))
    pipe = pipeline_cls.from_pretrained(
        model.model_id,
        vae=transparent_vae,
        **pipeline_kwargs,
    )
    if not model._layerdiffuse_applied:
        if is_sdxl:
            state_dict, network_alphas = pipeline_cls.lora_state_dict(
                lora_repo,
                weight_name=lora_weight_name,
                cache_dir=model.weights_cache_dir,
            )
            pipeline_cls.load_lora_into_unet(
                state_dict,
                network_alphas,
                pipe.unet,
                _pipeline=pipe,
            )
        else:
            lora_path = hf_hub_download(
                repo_id=lora_repo,
                filename=lora_weight_name,
                cache_dir=model.weights_cache_dir,
            )
            load_lora_to_unet(pipe.unet, lora_path, frames=1)
        model._layerdiffuse_applied = True
    effective_offload_mode = model.offload_mode
    if is_sdxl and effective_offload_mode == "sequential":
        effective_offload_mode = "model"
    return configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode=effective_offload_mode,
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
