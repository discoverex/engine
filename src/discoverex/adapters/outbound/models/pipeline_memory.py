from __future__ import annotations

from typing import Any, Literal

OffloadMode = Literal["none", "model", "sequential"]


def configure_diffusers_pipeline(
    pipe: Any,
    *,
    handle: Any,
    offload_mode: OffloadMode = "none",
    enable_attention_slicing: bool = False,
    enable_vae_slicing: bool = False,
    enable_vae_tiling: bool = False,
    enable_xformers_memory_efficient_attention: bool = False,
    enable_fp8_layerwise_casting: bool = False,
    enable_channels_last: bool = False,
) -> Any:
    torch_mod = _load_torch()
    if hasattr(pipe, "set_progress_bar_config"):
        pipe.set_progress_bar_config(disable=False)
    if enable_fp8_layerwise_casting:
        _enable_fp8_layerwise_casting(pipe, handle=handle, torch_mod=torch_mod)
    if enable_attention_slicing and hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing("auto")
    if enable_vae_slicing and hasattr(pipe, "enable_vae_slicing"):
        pipe.enable_vae_slicing()
    if enable_vae_tiling and hasattr(pipe, "enable_vae_tiling"):
        pipe.enable_vae_tiling()
    if (
        enable_xformers_memory_efficient_attention
        and hasattr(pipe, "enable_xformers_memory_efficient_attention")
    ):
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass
    if enable_channels_last and torch_mod is not None:
        unet = getattr(pipe, "unet", None)
        if unet is not None:
            try:
                unet.to(memory_format=torch_mod.channels_last)
            except Exception:
                pass
    if offload_mode == "sequential" and hasattr(pipe, "enable_sequential_cpu_offload"):
        pipe.enable_sequential_cpu_offload()
        return pipe
    if offload_mode == "model" and hasattr(pipe, "enable_model_cpu_offload"):
        pipe.enable_model_cpu_offload()
        return pipe
    return pipe.to(handle.device)


def _enable_fp8_layerwise_casting(pipe: Any, *, handle: Any, torch_mod: Any) -> None:
    if torch_mod is None or not hasattr(torch_mod, "float8_e4m3fn"):
        return
    compute_dtype = torch_mod.float16 if "16" in str(handle.dtype) else torch_mod.float32
    for component_name in ("unet", "transformer", "vae", "text_encoder", "text_encoder_2"):
        component = getattr(pipe, component_name, None)
        method = getattr(component, "enable_layerwise_casting", None)
        if not callable(method):
            continue
        try:
            method(
                storage_dtype=torch_mod.float8_e4m3fn,
                compute_dtype=compute_dtype,
            )
        except Exception:
            continue


def _load_torch() -> Any | None:
    try:
        import torch  # type: ignore
    except Exception:
        return None
    return torch
