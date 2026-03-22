from __future__ import annotations

# mypy: ignore-errors
from typing import Any

from ...pipeline_memory import configure_diffusers_pipeline


def _stdout_debug(message: str) -> None:
    print(f"[discoverex-debug] {message}", flush=True)


def load_pipeline(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    from diffusers import (  # type: ignore
        DPMSolverMultistepScheduler,
        EulerDiscreteScheduler,
        StableDiffusionPipeline,
        StableDiffusionXLPipeline,
        UniPCMultistepScheduler,
    )
    from huggingface_hub import hf_hub_download  # type: ignore
    from .rootonchair_sd15.loaders import load_lora_to_unet

    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    is_sdxl = "xl" in str(model.model_id).lower() or "sdxl" in str(model.model_id).lower()
    use_transparent_decoder = bool(getattr(model, "use_transparent_decoder", True))
    if is_sdxl:
        vae_model_id = "madebyollin/sdxl-vae-fp16-fix"
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
        vae_model_id = model.model_id
        pipeline_cls = StableDiffusionPipeline
        pipeline_kwargs = {
            "torch_dtype": torch_dtype,
            "safety_checker": None,
        }
        lora_repo = "LayerDiffusion/layerdiffusion-v1"
        lora_weight_name = "layer_sd15_transparent_attn.safetensors"
    if use_transparent_decoder:
        from safetensors.torch import load_file  # type: ignore
        from .rootonchair_vae import TransparentVAEDecoder

        if is_sdxl:
            vae = TransparentVAEDecoder.from_pretrained(
                vae_model_id,
                torch_dtype=torch_dtype,
            )
            decoder_filename = "vae_transparent_decoder.safetensors"
        else:
            vae = TransparentVAEDecoder.from_pretrained(
                vae_model_id,
                subfolder="vae",
                torch_dtype=torch_dtype,
            )
            decoder_filename = "layer_sd15_vae_transparent_decoder.safetensors"
        vae.config.force_upcast = False
        decoder_path = hf_hub_download(
            repo_id="LayerDiffusion/layerdiffusion-v1",
            filename=decoder_filename,
            cache_dir=model.weights_cache_dir,
        )
        vae.set_transparent_decoder(load_file(decoder_path))
    else:
        from diffusers import AutoencoderKL  # type: ignore

        if is_sdxl:
            vae = AutoencoderKL.from_pretrained(
                vae_model_id,
                torch_dtype=torch_dtype,
            )
        else:
            vae = AutoencoderKL.from_pretrained(
                vae_model_id,
                subfolder="vae",
                torch_dtype=torch_dtype,
            )
    pipe = pipeline_cls.from_pretrained(
        model.model_id,
        vae=vae,
        **pipeline_kwargs,
    )
    if not model._layerdiffuse_applied:
        if is_sdxl:
            pipe.load_lora_weights(
                lora_repo,
                weight_name=lora_weight_name,
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
    scheduler = getattr(pipe, "scheduler", None)
    if scheduler is not None:
        pipe.scheduler = _configure_scheduler(
            scheduler=scheduler,
            sampler_name=str(getattr(model, "sampler", "") or ""),
            dpm_scheduler_cls=DPMSolverMultistepScheduler,
            unipc_scheduler_cls=UniPCMultistepScheduler,
            euler_scheduler_cls=EulerDiscreteScheduler,
        )
    _stdout_debug(
        "object_pipeline_ready "
        f"model_id={model.model_id} sampler={getattr(model, 'sampler', '')} "
        f"is_sdxl={is_sdxl} effective_offload_mode={effective_offload_mode} "
        f"scheduler_cls={type(getattr(pipe, 'scheduler', None)).__name__}"
    )
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
    from .transparent_decode import LayerDiffuseTransparentDecoder

    _ = (model, handle)
    if not bool(getattr(model, "use_transparent_decoder", True)):
        return None
    return LayerDiffuseTransparentDecoder()


def _configure_scheduler(
    *,
    scheduler: Any,
    sampler_name: str,
    dpm_scheduler_cls: Any,
    unipc_scheduler_cls: Any,
    euler_scheduler_cls: Any,
) -> Any:
    normalized = sampler_name.strip().lower().replace("+", "p").replace(" ", "_")
    if normalized in {"", "default"}:
        return scheduler
    if normalized in {
        "dpmpp_sde_karras",
        "dpmpp_sde_2m_karras",
        "dpmpp_2m_sde_karras",
    }:
        return dpm_scheduler_cls.from_config(
            scheduler.config,
            algorithm_type="sde-dpmsolver++",
            use_karras_sigmas=True,
            solver_order=2,
        )
    if normalized in {"dpmpp_sde", "dpmpp_2m_sde"}:
        return dpm_scheduler_cls.from_config(
            scheduler.config,
            algorithm_type="sde-dpmsolver++",
            use_karras_sigmas=False,
            solver_order=2,
        )
    if normalized in {"unipc", "unipc_multistep"}:
        return unipc_scheduler_cls.from_config(scheduler.config)
    if normalized in {"euler", "euler_discrete"}:
        return euler_scheduler_cls.from_config(scheduler.config)
    raise ValueError(f"unsupported layerdiffuse sampler '{sampler_name}'")
