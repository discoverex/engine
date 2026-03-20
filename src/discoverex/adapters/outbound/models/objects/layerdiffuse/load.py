from __future__ import annotations

# mypy: ignore-errors
from dataclasses import dataclass
from typing import Any

from ...pipeline_memory import configure_diffusers_pipeline


@dataclass(slots=True)
class SdxlLayerDiffuseSpec:
    model_id: str
    revision: str
    torch_dtype: Any
    cache_dir: str
    variant: str | None
    lora_repo: str
    lora_weight_name: str
    decoder_repo: str
    decoder_filename: str


@dataclass(slots=True)
class SdxlTextComponents:
    tokenizer: Any
    tokenizer_2: Any
    text_encoder: Any
    text_encoder_2: Any


@dataclass(slots=True)
class SdxlDenoiseComponents:
    unet: Any
    scheduler: Any


@dataclass(slots=True)
class SdxlDecodeComponents:
    vae: Any


def _build_sdxl_spec(*, model: Any, handle: Any, torch: Any) -> SdxlLayerDiffuseSpec:
    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    return SdxlLayerDiffuseSpec(
        model_id=str(model.model_id),
        revision=str(model.revision),
        torch_dtype=torch_dtype,
        cache_dir=str(model.weights_cache_dir),
        variant="fp16" if "16" in handle.dtype else None,
        lora_repo="rootonchair/diffuser_layerdiffuse",
        lora_weight_name="diffuser_layer_xl_transparent_attn.safetensors",
        decoder_repo="LayerDiffusion/layerdiffusion-v1",
        decoder_filename="vae_transparent_decoder.safetensors",
    )


def load_sdxl_text_components(*, spec: SdxlLayerDiffuseSpec) -> SdxlTextComponents:
    from transformers import CLIPTextModel, CLIPTextModelWithProjection, CLIPTokenizer  # type: ignore

    tokenizer = CLIPTokenizer.from_pretrained(
        spec.model_id,
        revision=spec.revision,
        subfolder="tokenizer",
        cache_dir=spec.cache_dir,
    )
    tokenizer_2 = CLIPTokenizer.from_pretrained(
        spec.model_id,
        revision=spec.revision,
        subfolder="tokenizer_2",
        cache_dir=spec.cache_dir,
    )
    text_encoder = CLIPTextModel.from_pretrained(
        spec.model_id,
        revision=spec.revision,
        subfolder="text_encoder",
        cache_dir=spec.cache_dir,
        torch_dtype=spec.torch_dtype,
        variant=spec.variant,
    )
    text_encoder_2 = CLIPTextModelWithProjection.from_pretrained(
        spec.model_id,
        revision=spec.revision,
        subfolder="text_encoder_2",
        cache_dir=spec.cache_dir,
        torch_dtype=spec.torch_dtype,
        variant=spec.variant,
    )
    return SdxlTextComponents(
        tokenizer=tokenizer,
        tokenizer_2=tokenizer_2,
        text_encoder=text_encoder,
        text_encoder_2=text_encoder_2,
    )


def load_sdxl_denoise_components(*, spec: SdxlLayerDiffuseSpec) -> SdxlDenoiseComponents:
    from diffusers import EulerDiscreteScheduler, UNet2DConditionModel  # type: ignore
    from diffusers.loaders.lora_pipeline import StableDiffusionXLLoraLoaderMixin  # type: ignore

    unet = UNet2DConditionModel.from_pretrained(
        spec.model_id,
        revision=spec.revision,
        subfolder="unet",
        cache_dir=spec.cache_dir,
        torch_dtype=spec.torch_dtype,
        variant=spec.variant,
    )
    scheduler = EulerDiscreteScheduler.from_pretrained(
        spec.model_id,
        revision=spec.revision,
        subfolder="scheduler",
        cache_dir=spec.cache_dir,
    )
    state_dict, network_alphas, metadata = StableDiffusionXLLoraLoaderMixin.lora_state_dict(
        spec.lora_repo,
        revision="main",
        cache_dir=spec.cache_dir,
        weight_name=spec.lora_weight_name,
        unet_config=unet.config,
        return_lora_metadata=True,
    )
    StableDiffusionXLLoraLoaderMixin.load_lora_into_unet(
        state_dict,
        network_alphas=network_alphas,
        unet=unet,
        metadata=metadata,
    )
    return SdxlDenoiseComponents(unet=unet, scheduler=scheduler)


def load_sdxl_decode_components(*, spec: SdxlLayerDiffuseSpec) -> SdxlDecodeComponents:
    from huggingface_hub import hf_hub_download  # type: ignore
    from safetensors.torch import load_file  # type: ignore
    from .rootonchair_vae import TransparentVAEDecoder

    vae = TransparentVAEDecoder.from_pretrained(
        "madebyollin/sdxl-vae-fp16-fix",
        torch_dtype=spec.torch_dtype,
    )
    vae.config.force_upcast = False
    decoder_path = hf_hub_download(
        repo_id=spec.decoder_repo,
        filename=spec.decoder_filename,
        cache_dir=spec.cache_dir,
    )
    vae.set_transparent_decoder(load_file(decoder_path))
    return SdxlDecodeComponents(vae=vae)


def load_pipeline(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline  # type: ignore
    from huggingface_hub import hf_hub_download  # type: ignore
    from safetensors.torch import load_file  # type: ignore
    from .rootonchair_vae import TransparentVAEDecoder
    from .rootonchair_sd15.loaders import load_lora_to_unet

    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    is_sdxl = "xl" in str(model.model_id).lower() or "sdxl" in str(model.model_id).lower()
    runtime_strategy = str(getattr(model, "runtime_strategy", "pipeline") or "pipeline")
    if is_sdxl:
        pipeline_cls = StableDiffusionXLPipeline
        pipeline_kwargs: dict[str, Any] = {
            "revision": model.revision,
            "torch_dtype": torch_dtype,
            "variant": "fp16" if "16" in handle.dtype else None,
            "use_safetensors": True,
            "add_watermarker": False,
        }
        sdxl_spec = _build_sdxl_spec(model=model, handle=handle, torch=torch)
        if runtime_strategy == "component_staged":
            return sdxl_spec
        transparent_vae = load_sdxl_decode_components(spec=sdxl_spec).vae
        lora_repo = sdxl_spec.lora_repo
        lora_weight_name = sdxl_spec.lora_weight_name
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
    standard_sdxl_base = str(model.model_id) == "stabilityai/stable-diffusion-xl-base-1.0"
    if is_sdxl and not standard_sdxl_base and effective_offload_mode == "sequential":
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
