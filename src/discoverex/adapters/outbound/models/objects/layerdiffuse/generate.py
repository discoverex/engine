from __future__ import annotations

import inspect
import sys
from typing import Any

from PIL import Image  # type: ignore


def _debug(message: str) -> None:
    print(f"[layerdiffuse-debug] {message}", file=sys.stderr, flush=True)


def _unwrap_runtime(pipe_or_bundle: Any) -> tuple[str, Any]:
    kind = str(getattr(pipe_or_bundle, "kind", "pipeline") or "pipeline")
    payload = getattr(pipe_or_bundle, "payload", pipe_or_bundle)
    return kind, payload


def _move_component(component: Any, device: Any) -> None:
    if component is None:
        return
    try:
        component.to(device)
    except Exception:
        return


def _module_device(component: Any) -> str:
    if component is None:
        return "missing"
    try:
        parameter = next(component.parameters())
    except Exception:
        return "unknown"
    try:
        return str(parameter.device)
    except Exception:
        return "unknown"


def _tensor_device(value: Any) -> str:
    try:
        return str(value.device)
    except Exception:
        return "unknown"


def _to_rgba_image(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGBA")
    try:
        import numpy as np  # type: ignore
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise TypeError(f"unsupported image output type={type(image)!r}") from exc
    if isinstance(image, torch.Tensor):
        tensor = image.detach().float().cpu()
        if tensor.ndim == 4:
            tensor = tensor[0]
        if tensor.ndim != 3:
            raise TypeError(f"unsupported tensor image shape={tuple(tensor.shape)!r}")
        if tensor.shape[0] in (3, 4):
            tensor = tensor.permute(1, 2, 0)
        array = tensor.numpy()
        if array.dtype != np.uint8:
            array = ((array + 1.0) / 2.0 if array.min() < 0 else array).clip(0.0, 1.0)
            array = (array * 255.0).round().astype(np.uint8)
        if array.shape[-1] == 3:
            alpha = np.full((*array.shape[:2], 1), 255, dtype=np.uint8)
            array = np.concatenate([array, alpha], axis=-1)
        return Image.fromarray(array, mode="RGBA")
    return Image.fromarray(image, mode="RGBA")


def _to_rgba_images(images: Any) -> list[Image.Image]:
    try:
        import numpy as np  # type: ignore
        import torch  # type: ignore
    except Exception:
        np = None
        torch = None
    if isinstance(images, list):
        return [_to_rgba_image(image) for image in images]
    if torch is not None and isinstance(images, torch.Tensor) and images.ndim == 4:
        return [_to_rgba_image(image) for image in images]
    if np is not None and isinstance(images, np.ndarray) and images.ndim == 4:
        return [_to_rgba_image(image) for image in images]
    return [_to_rgba_image(images)]


def _raise_if_vram_limit_exceeded(*, limit_gb: float | None) -> None:
    if limit_gb is None or limit_gb <= 0:
        return
    try:
        import torch  # type: ignore
    except Exception:
        return
    if not torch.cuda.is_available():
        return
    reserved_bytes = int(torch.cuda.max_memory_reserved())
    limit_bytes = int(limit_gb * 1024 * 1024 * 1024)
    if reserved_bytes <= limit_bytes:
        return
    raise RuntimeError(
        "object generation exceeded vram limit "
        f"reserved_gb={reserved_bytes / (1024 ** 3):.2f} limit_gb={limit_gb:.2f}"
    )


def _offload_text_encoders(*, pipe: Any) -> None:
    try:
        import torch  # type: ignore
    except Exception:
        torch = None
    for component_name in ("text_encoder", "text_encoder_2"):
        component = getattr(pipe, component_name, None)
        if component is None:
            continue
        try:
            component.to("cpu")
        except Exception:
            continue
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def _offload_unet_stack(*, pipe: Any) -> None:
    try:
        import torch  # type: ignore
    except Exception:
        torch = None
    for component_name in ("unet",):
        component = getattr(pipe, component_name, None)
        if component is None:
            continue
        try:
            component.to("cpu")
        except Exception:
            continue
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def _offload_decode_stack(*, pipe: Any, decoder: Any) -> None:
    try:
        import torch  # type: ignore
    except Exception:
        torch = None
    for component in (getattr(pipe, "vae", None), decoder):
        if component is None:
            continue
        try:
            component.to("cpu")
        except Exception:
            continue
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def _offload_component_runtime(*, runtime: Any, include_text: bool, include_unet: bool, include_vae: bool) -> None:
    if include_text:
        _move_component(getattr(runtime, "text_encoder", None), "cpu")
        _move_component(getattr(runtime, "text_encoder_2", None), "cpu")
    if include_unet:
        _move_component(getattr(runtime, "unet", None), "cpu")
    if include_vae:
        _move_component(getattr(runtime, "vae", None), "cpu")
    try:
        import torch  # type: ignore
    except Exception:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _prepare_decode_stack(*, pipe: Any, execution_device: Any) -> None:
    try:
        import torch  # type: ignore
        from accelerate.hooks import remove_hook_from_module  # type: ignore
    except Exception:
        torch = None
        remove_hook_from_module = None
    vae = getattr(pipe, "vae", None)
    if vae is None:
        return
    if callable(remove_hook_from_module):
        try:
            remove_hook_from_module(vae, recurse=True)
        except Exception:
            pass
    try:
        vae.to(execution_device)
    except Exception:
        pass
    decoder = getattr(vae, "transparent_decoder", None)
    if decoder is not None:
        try:
            decoder.to(execution_device)
        except Exception:
            pass
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def _decode_latents_to_rgba_images(*, pipe: Any, latents: Any) -> list[Image.Image]:
    decoded = pipe.vae.decode(latents, return_dict=False)[0]
    return _to_rgba_images(decoded)


def _decode_latents_with_components(*, runtime: Any, execution_device: Any, latents: Any) -> list[Image.Image]:
    _move_component(getattr(runtime, "vae", None), execution_device)
    decoded = runtime.vae.decode(latents, return_dict=False)[0]
    return _to_rgba_images(decoded)


def _build_prompt_embeds(
    *,
    pipe: Any,
    execution_device: Any,
    prompts: str | list[str],
    negative_prompts: str | list[str],
    guidance_scale: float,
) -> tuple[Any, Any, Any, Any]:
    _debug("encode_prompt:start")
    prompt_embeds = None
    negative_prompt_embeds = None
    pooled_prompt_embeds = None
    negative_pooled_prompt_embeds = None
    encode_prompt = getattr(pipe, "encode_prompt", None)
    if not callable(encode_prompt):
        return (
            prompt_embeds,
            negative_prompt_embeds,
            pooled_prompt_embeds,
            negative_pooled_prompt_embeds,
        )
    encode_signature = inspect.signature(encode_prompt)
    encode_kwargs: dict[str, Any] = {
        "prompt": prompts,
        "device": execution_device,
        "num_images_per_prompt": 1,
        "do_classifier_free_guidance": guidance_scale > 1.0,
        "negative_prompt": negative_prompts,
    }
    if "prompt_2" in encode_signature.parameters:
        encode_kwargs["prompt_2"] = prompts
    if "negative_prompt_2" in encode_signature.parameters:
        encode_kwargs["negative_prompt_2"] = negative_prompts
    encoded = encode_prompt(**encode_kwargs)
    _debug("encode_prompt:end")
    if isinstance(encoded, tuple) and len(encoded) == 4:
        (
            prompt_embeds,
            negative_prompt_embeds,
            pooled_prompt_embeds,
            negative_pooled_prompt_embeds,
        ) = encoded
    elif isinstance(encoded, tuple) and len(encoded) == 2:
        prompt_embeds, negative_prompt_embeds = encoded
    else:
        raise TypeError(
            "unsupported encode_prompt return contract "
            f"type={type(encoded)!r} len={len(encoded) if isinstance(encoded, tuple) else 'n/a'}"
        )
    return (
        prompt_embeds,
        negative_prompt_embeds,
        pooled_prompt_embeds,
        negative_pooled_prompt_embeds,
    )


def _build_prompt_embeds_with_components(
    *,
    runtime: Any,
    execution_device: Any,
    prompts: str | list[str],
    negative_prompts: str | list[str],
    guidance_scale: float,
) -> tuple[Any, Any, Any, Any]:
    _move_component(getattr(runtime, "text_encoder", None), execution_device)
    _move_component(getattr(runtime, "text_encoder_2", None), execution_device)
    return _build_prompt_embeds(
        pipe=runtime.pipe,
        execution_device=execution_device,
        prompts=prompts,
        negative_prompts=negative_prompts,
        guidance_scale=guidance_scale,
    )


def _sample_latents(
    *,
    pipe: Any,
    prompts: str | list[str],
    negative_prompts: str | list[str],
    width: int,
    height: int,
    generator: Any,
    num_inference_steps: int,
    guidance_scale: float,
    execution_device: Any,
    max_vram_gb: float | None,
) -> Any:
    _debug(
        "sample_latents:start "
        f"width={width} height={height} steps={num_inference_steps} guidance={guidance_scale}"
    )
    (
        prompt_embeds,
        negative_prompt_embeds,
        pooled_prompt_embeds,
        negative_pooled_prompt_embeds,
    ) = _build_prompt_embeds(
        pipe=pipe,
        execution_device=execution_device,
        prompts=prompts,
        negative_prompts=negative_prompts,
        guidance_scale=guidance_scale,
    )
    if prompt_embeds is not None:
        _offload_text_encoders(pipe=pipe)
        _debug("text_encoders:offloaded")
        _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    call_signature = inspect.signature(pipe.__call__)
    pipe_kwargs: dict[str, Any] = {
        "prompt": None if prompt_embeds is not None else prompts,
        "negative_prompt": None if negative_prompt_embeds is not None else negative_prompts,
        "num_inference_steps": num_inference_steps,
        "num_images_per_prompt": 1,
        "guidance_scale": guidance_scale,
        "width": width,
        "height": height,
        "generator": generator,
        "output_type": "latent",
        "prompt_embeds": prompt_embeds,
        "negative_prompt_embeds": negative_prompt_embeds,
        "return_dict": False,
    }
    if "pooled_prompt_embeds" in call_signature.parameters:
        pipe_kwargs["pooled_prompt_embeds"] = pooled_prompt_embeds
    if "negative_pooled_prompt_embeds" in call_signature.parameters:
        pipe_kwargs["negative_pooled_prompt_embeds"] = negative_pooled_prompt_embeds
    _debug("denoise:start")
    result = pipe(**pipe_kwargs)
    _debug("denoise:end")
    _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    latents = result[0] if isinstance(result, tuple) else result
    _offload_unet_stack(pipe=pipe)
    _debug("unet:offloaded")
    _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    return latents


def _sample_latents_with_components(
    *,
    runtime: Any,
    prompts: str | list[str],
    negative_prompts: str | list[str],
    width: int,
    height: int,
    generator: Any,
    num_inference_steps: int,
    guidance_scale: float,
    execution_device: Any,
    max_vram_gb: float | None,
) -> Any:
    import torch  # type: ignore

    _debug(
        "sample_latents_components:start "
        f"width={width} height={height} steps={num_inference_steps} guidance={guidance_scale}"
    )
    (
        prompt_embeds,
        negative_prompt_embeds,
        pooled_prompt_embeds,
        negative_pooled_prompt_embeds,
    ) = _build_prompt_embeds_with_components(
        runtime=runtime,
        execution_device=execution_device,
        prompts=prompts,
        negative_prompts=negative_prompts,
        guidance_scale=guidance_scale,
    )
    _offload_component_runtime(runtime=runtime, include_text=True, include_unet=False, include_vae=False)
    _debug("text_components:offloaded")

    batch_size = len(prompts) if isinstance(prompts, list) else 1
    num_images_per_prompt = 1
    do_cfg = guidance_scale > 1.0
    _move_component(runtime.unet, execution_device)
    _debug(
        "component_runtime:devices "
        f"execution_device={execution_device} "
        f"text_encoder={_module_device(runtime.text_encoder)} "
        f"text_encoder_2={_module_device(runtime.text_encoder_2)} "
        f"unet={_module_device(runtime.unet)} "
        f"vae={_module_device(runtime.vae)}"
    )

    runtime.scheduler.set_timesteps(num_inference_steps, device=execution_device)
    timesteps = runtime.scheduler.timesteps
    latents = runtime.pipe.prepare_latents(
        batch_size * num_images_per_prompt,
        runtime.unet.config.in_channels,
        height,
        width,
        prompt_embeds.dtype,
        execution_device,
        generator,
        None,
    )
    extra_step_kwargs = runtime.pipe.prepare_extra_step_kwargs(generator, 0.0)
    add_text_embeds = pooled_prompt_embeds
    text_encoder_projection_dim = int(runtime.text_encoder_2.config.projection_dim)
    add_time_ids = runtime.pipe._get_add_time_ids(
        (height, width),
        (0, 0),
        (height, width),
        dtype=prompt_embeds.dtype,
        text_encoder_projection_dim=text_encoder_projection_dim,
    )
    negative_add_time_ids = add_time_ids
    if do_cfg:
        prompt_embeds = torch.cat([negative_prompt_embeds, prompt_embeds], dim=0)
        add_text_embeds = torch.cat([negative_pooled_prompt_embeds, add_text_embeds], dim=0)
        add_time_ids = torch.cat([negative_add_time_ids, add_time_ids], dim=0)
    prompt_embeds = prompt_embeds.to(execution_device)
    add_text_embeds = add_text_embeds.to(execution_device)
    add_time_ids = add_time_ids.to(execution_device).repeat(batch_size * num_images_per_prompt, 1)
    _debug(
        "component_runtime:tensors "
        f"latents={_tensor_device(latents)} "
        f"prompt_embeds={_tensor_device(prompt_embeds)} "
        f"add_text_embeds={_tensor_device(add_text_embeds)} "
        f"add_time_ids={_tensor_device(add_time_ids)}"
    )
    timestep_cond = None
    if runtime.unet.config.time_cond_proj_dim is not None:
        guidance_scale_tensor = torch.tensor(guidance_scale - 1).repeat(batch_size * num_images_per_prompt)
        timestep_cond = runtime.pipe.get_guidance_scale_embedding(
            guidance_scale_tensor,
            embedding_dim=runtime.unet.config.time_cond_proj_dim,
        ).to(device=execution_device, dtype=latents.dtype)

    _debug("denoise_components:start")
    for timestep in timesteps:
        latent_model_input = torch.cat([latents] * 2) if do_cfg else latents
        latent_model_input = runtime.scheduler.scale_model_input(latent_model_input, timestep)
        added_cond_kwargs = {"text_embeds": add_text_embeds, "time_ids": add_time_ids}
        noise_pred = runtime.unet(
            latent_model_input,
            timestep,
            encoder_hidden_states=prompt_embeds,
            timestep_cond=timestep_cond,
            cross_attention_kwargs=None,
            added_cond_kwargs=added_cond_kwargs,
            return_dict=False,
        )[0]
        if do_cfg:
            noise_pred_uncond, noise_pred_text = noise_pred.chunk(2)
            noise_pred = noise_pred_uncond + guidance_scale * (noise_pred_text - noise_pred_uncond)
        latents_dtype = latents.dtype
        latents = runtime.scheduler.step(
            noise_pred,
            timestep,
            latents,
            **extra_step_kwargs,
            return_dict=False,
        )[0]
        if latents.dtype != latents_dtype and getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            latents = latents.to(latents_dtype)
    _debug("denoise_components:end")
    _offload_component_runtime(runtime=runtime, include_text=False, include_unet=True, include_vae=False)
    _debug("unet_components:offloaded")
    _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    return latents


def generate_rgba(
    *,
    model: Any,
    handle: Any,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    seed: int | None,
    num_inference_steps: int,
    guidance_scale: float,
    max_vram_gb: float | None = None,
) -> Any:
    import torch  # type: ignore

    _debug(f"generate_rgba:start model_id={getattr(model, 'model_id', 'unknown')}")
    pipe_bundle = model._load_pipeline(handle)
    runtime_kind, runtime = _unwrap_runtime(pipe_bundle)
    _debug(f"pipeline:loaded kind={runtime_kind}")
    execution_device = getattr(getattr(runtime, "pipe", runtime), "_execution_device", handle.device)
    _debug(
        "runtime:config "
        f"handle_device={getattr(handle, 'device', 'unknown')} "
        f"execution_device={execution_device} "
        f"runtime_kind={runtime_kind} "
        f"width={width} height={height} steps={num_inference_steps} guidance={guidance_scale}"
    )
    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    if runtime_kind == "component_staged":
        latents = _sample_latents_with_components(
            runtime=runtime,
            prompts=prompt,
            negative_prompts=negative_prompt,
            width=width,
            height=height,
            generator=generator,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            execution_device=execution_device,
            max_vram_gb=max_vram_gb,
        )
        _debug("decode_components:start")
        images = _decode_latents_with_components(runtime=runtime, execution_device=execution_device, latents=latents)
        _debug("decode_components:end")
        _offload_component_runtime(runtime=runtime, include_text=False, include_unet=False, include_vae=True)
        _debug("vae_components:offloaded")
    else:
        latents = _sample_latents(
            pipe=runtime,
            prompts=prompt,
            negative_prompts=negative_prompt,
            width=width,
            height=height,
            generator=generator,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            execution_device=execution_device,
            max_vram_gb=max_vram_gb,
        )
        _debug("decode:prepare")
        _prepare_decode_stack(pipe=runtime, execution_device=execution_device)
        _debug("decode:start")
        images = _decode_latents_to_rgba_images(pipe=runtime, latents=latents)
        _debug("decode:end")
        _offload_decode_stack(pipe=runtime, decoder=None)
        _debug("decode_stack:offloaded")
    image = images[0]
    return _to_rgba_image(image)


def generate_rgba_batch(
    *,
    model: Any,
    handle: Any,
    prompts: list[str],
    negative_prompts: list[str],
    width: int,
    height: int,
    seed: int | None,
    num_inference_steps: int,
    guidance_scale: float,
    max_vram_gb: float | None = None,
) -> list[Image.Image]:
    import torch  # type: ignore

    if not prompts:
        return []
    if len(prompts) != len(negative_prompts):
        raise ValueError("prompts and negative_prompts must have the same length")
    _debug(
        "generate_rgba_batch:start "
        f"model_id={getattr(model, 'model_id', 'unknown')} count={len(prompts)}"
    )
    pipe_bundle = model._load_pipeline(handle)
    runtime_kind, runtime = _unwrap_runtime(pipe_bundle)
    _debug(f"pipeline:loaded kind={runtime_kind}")
    if runtime_kind == "component_staged":
        raise RuntimeError("component_staged runtime only supports single-image generation")
    execution_device = getattr(runtime, "_execution_device", handle.device)
    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    latents = _sample_latents(
        pipe=runtime,
        prompts=prompts,
        negative_prompts=negative_prompts,
        width=width,
        height=height,
        generator=generator,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        execution_device=execution_device,
        max_vram_gb=max_vram_gb,
    )
    _debug("decode:prepare")
    _prepare_decode_stack(pipe=runtime, execution_device=execution_device)
    _debug("decode:start")
    images = _decode_latents_to_rgba_images(pipe=runtime, latents=latents)
    _debug("decode:end")
    _offload_decode_stack(pipe=runtime, decoder=None)
    _debug("decode_stack:offloaded")
    return _to_rgba_images(images)
