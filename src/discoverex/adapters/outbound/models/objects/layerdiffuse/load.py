from __future__ import annotations

# mypy: ignore-errors
from pathlib import Path
from typing import Any

from ...pipeline_memory import configure_diffusers_pipeline

_REQUIRED_SNAPSHOT_FILES = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "tokenizer/vocab.json",
    "tokenizer/merges.txt",
    "tokenizer/special_tokens_map.json",
    "tokenizer/tokenizer_config.json",
    "tokenizer_2/vocab.json",
    "tokenizer_2/merges.txt",
    "tokenizer_2/special_tokens_map.json",
    "tokenizer_2/tokenizer_config.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors",
    "text_encoder/model.fp16.safetensors",
    "text_encoder_2/model.fp16.safetensors",
)


def _stdout_debug(message: str) -> None:
    print(f"[discoverex-debug] {message}", flush=True)


_SDXL_ATTN_OFFSET_URL = (
    "https://huggingface.co/lllyasviel/LayerDiffuse_Diffusers/resolve/main/"
    "ld_diffusers_sdxl_attn.safetensors"
)
_SDXL_TRANSPARENT_DECODER_URL = (
    "https://huggingface.co/lllyasviel/LayerDiffuse_Diffusers/resolve/main/"
    "ld_diffusers_sdxl_vae_transparent_decoder.safetensors"
)


def load_pipeline(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    import diffusers  # type: ignore
    from huggingface_hub import hf_hub_download  # type: ignore
    from .rootonchair_sd15.loaders import load_lora_to_unet

    AutoPipelineForText2Image = getattr(
        diffusers,
        "AutoPipelineForText2Image",
        getattr(diffusers, "StableDiffusionXLPipeline"),
    )
    AutoencoderKL = getattr(diffusers, "AutoencoderKL")
    DPMSolverMultistepScheduler = getattr(diffusers, "DPMSolverMultistepScheduler")
    EulerDiscreteScheduler = getattr(diffusers, "EulerDiscreteScheduler")
    StableDiffusionPipeline = getattr(diffusers, "StableDiffusionPipeline")
    StableDiffusionXLPipeline = getattr(diffusers, "StableDiffusionXLPipeline")
    UniPCMultistepScheduler = getattr(diffusers, "UniPCMultistepScheduler")

    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    pipeline_variant = str(getattr(model, "pipeline_variant", "") or "").strip().lower()
    if pipeline_variant == "sd15_layerdiffuse_transparent":
        return _load_sd15_transparent_pipeline(
            model=model,
            torch_dtype=torch_dtype,
            stable_diffusion_pipeline_cls=StableDiffusionPipeline,
            dpm_scheduler_cls=DPMSolverMultistepScheduler,
            unipc_scheduler_cls=UniPCMultistepScheduler,
            euler_scheduler_cls=EulerDiscreteScheduler,
            handle=handle,
        )
    is_sdxl = "xl" in str(model.model_id).lower() or "sdxl" in str(model.model_id).lower()
    if is_sdxl:
        return _load_sdxl_transparent_pipeline(
            model=model,
            torch_dtype=torch_dtype,
            auto_pipeline_cls=AutoPipelineForText2Image,
            autoencoder_cls=AutoencoderKL,
            dpm_scheduler_cls=DPMSolverMultistepScheduler,
            unipc_scheduler_cls=UniPCMultistepScheduler,
            euler_scheduler_cls=EulerDiscreteScheduler,
            handle=handle,
        )
    else:
        vae_model_id = model.model_id
        pipeline_cls = StableDiffusionPipeline
        pipeline_kwargs = {
            "torch_dtype": torch_dtype,
            "safety_checker": None,
        }
        lora_repo = "LayerDiffusion/layerdiffusion-v1"
        lora_weight_name = "layer_sd15_transparent_attn.safetensors"

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


def _load_sdxl_transparent_pipeline(
    *,
    model: Any,
    torch_dtype: Any,
    auto_pipeline_cls: Any,
    autoencoder_cls: Any,
    dpm_scheduler_cls: Any,
    unipc_scheduler_cls: Any,
    euler_scheduler_cls: Any,
    handle: Any,
) -> Any:
    import importlib

    import safetensors.torch as sf  # type: ignore

    variant = "fp16" if "16" in handle.dtype else None
    base_vae = autoencoder_cls.from_pretrained(
        "madebyollin/sdxl-vae-fp16-fix",
        torch_dtype=torch_dtype,
    )
    pipe = _from_pretrained_with_cache_policy(
        model=model,
        loader=auto_pipeline_cls.from_pretrained,
        variant=variant,
        torch_dtype=torch_dtype,
        extra_kwargs={"vae": base_vae},
    )
    pipe.scheduler = _configure_scheduler(
        scheduler=pipe.scheduler,
        sampler_name=str(getattr(model, "sampler", "") or ""),
        dpm_scheduler_cls=dpm_scheduler_cls,
        unipc_scheduler_cls=unipc_scheduler_cls,
        euler_scheduler_cls=euler_scheduler_cls,
    )
    if not model._layerdiffuse_applied:
        attn_path = _download_weight(
            cache_dir=model.weights_cache_dir,
            url=_SDXL_ATTN_OFFSET_URL,
            filename="ld_diffusers_sdxl_attn.safetensors",
        )
        offset = sf.load_file(str(attn_path))
        base_state = pipe.unet.state_dict()
        merged_state = {
            key: base_state[key] + offset[key] if key in offset else base_state[key]
            for key in base_state
        }
        pipe.unet.load_state_dict(merged_state, strict=True)
        model._layerdiffuse_applied = True
    if getattr(model, "_transparent_decoder", None) is None:
        transparent_vae = importlib.import_module(
            "discoverex.adapters.outbound.models.layerdiffuse_transparent_vae"
        )
        decoder_path = _download_weight(
            cache_dir=model.weights_cache_dir,
            url=_SDXL_TRANSPARENT_DECODER_URL,
            filename="ld_diffusers_sdxl_vae_transparent_decoder.safetensors",
        )
        setattr(
            model,
            "_transparent_decoder",
            transparent_vae.TransparentVAEDecoder(
            str(decoder_path),
            dtype=torch_dtype,
            ),
        )
    pipe._layerdiffuse_base_vae = base_vae
    _stdout_debug(
        "object_pipeline_ready "
        f"model_id={model.model_id} sampler={getattr(model, 'sampler', '')} "
        "is_sdxl=True transparent_decoder=legacy_layerdiffuse "
        f"scheduler_cls={type(getattr(pipe, 'scheduler', None)).__name__}"
    )
    return configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode="model" if model.offload_mode == "sequential" else model.offload_mode,
        enable_attention_slicing=model.enable_attention_slicing,
        enable_vae_slicing=model.enable_vae_slicing,
        enable_vae_tiling=model.enable_vae_tiling,
        enable_xformers_memory_efficient_attention=model.enable_xformers_memory_efficient_attention,
        enable_fp8_layerwise_casting=model.enable_fp8_layerwise_casting,
        enable_channels_last=model.enable_channels_last,
    )


def _from_pretrained_with_cache_policy(
    *,
    model: Any,
    loader: Any,
    variant: str | None,
    torch_dtype: Any,
    extra_kwargs: dict[str, Any] | None = None,
) -> Any:
    cache_dir = _diffusers_cache_dir(model)
    kwargs = {
        "revision": model.revision,
        "torch_dtype": torch_dtype,
        "variant": variant,
        "use_safetensors": True,
        "add_watermarker": False,
        "cache_dir": cache_dir,
        **(extra_kwargs or {}),
    }
    if _should_try_local_first(model, cache_dir):
        _stdout_debug(
            "object_pipeline_local_only_attempt "
            f"model_id={model.model_id} cache_dir={cache_dir} snapshot={_snapshot_dir(model, cache_dir) or 'missing'}"
        )
        try:
            return loader(model.model_id, local_files_only=True, **kwargs)
        except Exception as exc:
            _stdout_debug(
                "object_pipeline_local_only_failed "
                f"model_id={model.model_id} cache_dir={cache_dir} reason={exc}"
            )
            if not bool(getattr(model, "allow_remote_model_fetch", True)):
                raise
    _stdout_debug(
        "object_pipeline_remote_fallback "
        f"model_id={model.model_id} cache_dir={cache_dir} policy={getattr(model, 'model_cache_policy', 'local_first')}"
    )
    return loader(model.model_id, **kwargs)


def _should_try_local_first(model: Any, cache_dir: str) -> bool:
    policy = str(getattr(model, "model_cache_policy", "local_first") or "").strip().lower()
    if policy not in {"local_first", "remote_first"}:
        policy = "local_first"
    if policy != "local_first":
        return False
    if str(getattr(model, "required_local_snapshot", "") or "").strip() and _snapshot_dir(model, cache_dir) is None:
        return False
    return not _missing_snapshot_files(model, cache_dir)


def _missing_snapshot_files(model: Any, cache_dir: str) -> list[str]:
    snapshot = _snapshot_dir(model, cache_dir)
    if snapshot is None:
        return list(_REQUIRED_SNAPSHOT_FILES)
    root = Path(snapshot)
    return [relative for relative in _REQUIRED_SNAPSHOT_FILES if not (root / relative).exists()]


def _snapshot_dir(model: Any, cache_dir: str) -> str | None:
    repo_root = Path(cache_dir) / "hub" / _repo_cache_key(model.model_id)
    snapshot_ref = str(getattr(model, "required_local_snapshot", "") or "").strip()
    if not snapshot_ref:
        ref_path = repo_root / "refs" / str(getattr(model, "revision", "main") or "main")
        if ref_path.exists():
            snapshot_ref = ref_path.read_text(encoding="utf-8").strip()
    if not snapshot_ref:
        return None
    snapshot_path = repo_root / "snapshots" / snapshot_ref
    if not snapshot_path.exists():
        return None
    return str(snapshot_path)


def _diffusers_cache_dir(model: Any) -> str:
    hf_home = str(getattr(model, "hf_home", "") or "").strip()
    if hf_home:
        return str(Path(hf_home).expanduser())
    model_cache_dir = str(getattr(model, "model_cache_dir", "") or "").strip()
    if model_cache_dir:
        return str(Path(model_cache_dir).expanduser() / "hf")
    weights_cache_dir = Path(str(getattr(model, "weights_cache_dir", "") or "")).expanduser()
    if weights_cache_dir.name == "layerdiffuse":
        return str(weights_cache_dir.parent / "hf")
    return str(weights_cache_dir / "hf")


def _repo_cache_key(model_id: str) -> str:
    return f"models--{model_id.replace('/', '--')}"


def _load_sd15_transparent_pipeline(
    *,
    model: Any,
    torch_dtype: Any,
    stable_diffusion_pipeline_cls: Any,
    dpm_scheduler_cls: Any,
    unipc_scheduler_cls: Any,
    euler_scheduler_cls: Any,
    handle: Any,
) -> Any:
    from diffusers import AutoencoderKL  # type: ignore
    from huggingface_hub import hf_hub_download  # type: ignore
    from safetensors.torch import load_file  # type: ignore
    from .rootonchair_sd15.loaders import load_lora_to_unet
    from .rootonchair_sd15.models.modules import TransparentVAEDecoder

    model_id = str(getattr(model, "model_id", "") or "").strip() or "runwayml/stable-diffusion-v1-5"
    weights_repo = (
        str(getattr(model, "weights_repo", "") or "").strip()
        or "LayerDiffusion/layerdiffusion-v1"
    )
    transparent_decoder_weight_name = (
        str(getattr(model, "transparent_decoder_weight_name", "") or "").strip()
        or "layer_sd15_vae_transparent_decoder.safetensors"
    )
    attn_weight_name = (
        str(getattr(model, "attn_weight_name", "") or "").strip()
        or "layer_sd15_transparent_attn.safetensors"
    )
    vae = TransparentVAEDecoder.from_pretrained(
        model_id,
        subfolder="vae",
        torch_dtype=torch_dtype,
    )
    vae.config.force_upcast = False
    decoder_path = hf_hub_download(
        repo_id=weights_repo,
        filename=transparent_decoder_weight_name,
        cache_dir=model.weights_cache_dir,
    )
    vae.set_transparent_decoder(load_file(decoder_path))
    pipe = stable_diffusion_pipeline_cls.from_pretrained(
        model_id,
        vae=vae,
        torch_dtype=torch_dtype,
        safety_checker=None,
    )
    if not model._layerdiffuse_applied:
        attn_path = hf_hub_download(
            repo_id=weights_repo,
            filename=attn_weight_name,
            cache_dir=model.weights_cache_dir,
        )
        load_lora_to_unet(pipe.unet, attn_path, frames=1)
        model._layerdiffuse_applied = True
    scheduler = getattr(pipe, "scheduler", None)
    if scheduler is not None:
        pipe.scheduler = _configure_scheduler(
            scheduler=scheduler,
            sampler_name=str(getattr(model, "sampler", "") or ""),
            dpm_scheduler_cls=dpm_scheduler_cls,
            unipc_scheduler_cls=unipc_scheduler_cls,
            euler_scheduler_cls=euler_scheduler_cls,
        )
    _stdout_debug(
        "object_pipeline_ready "
        f"model_id={model_id} sampler={getattr(model, 'sampler', '')} "
        "is_sdxl=False pipeline_variant=sd15_layerdiffuse_transparent "
        f"scheduler_cls={type(getattr(pipe, 'scheduler', None)).__name__}"
    )
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


def _download_weight(*, cache_dir: str, url: str, filename: str) -> Path:
    from torch.hub import download_url_to_file  # type: ignore

    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    if target.exists():
        return target
    temp = target.with_suffix(target.suffix + ".tmp")
    download_url_to_file(url, str(temp))
    temp.replace(target)
    return target


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


def reset_scheduler(*, model: Any, pipe: Any) -> None:
    import diffusers  # type: ignore

    scheduler = getattr(pipe, "scheduler", None)
    if scheduler is None:
        return
    DPMSolverMultistepScheduler = getattr(diffusers, "DPMSolverMultistepScheduler")
    UniPCMultistepScheduler = getattr(diffusers, "UniPCMultistepScheduler")
    EulerDiscreteScheduler = getattr(diffusers, "EulerDiscreteScheduler")
    pipe.scheduler = _configure_scheduler(
        scheduler=scheduler,
        sampler_name=str(getattr(model, "sampler", "") or ""),
        dpm_scheduler_cls=DPMSolverMultistepScheduler,
        unipc_scheduler_cls=UniPCMultistepScheduler,
        euler_scheduler_cls=EulerDiscreteScheduler,
    )
    _stdout_debug(
        "object_scheduler_reset "
        f"model_id={getattr(model, 'model_id', '')} "
        f"scheduler_cls={type(getattr(pipe, 'scheduler', None)).__name__}"
    )
