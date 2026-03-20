from __future__ import annotations

from typing import Any

from PIL import Image  # type: ignore


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

    pipe = model._load_pipeline(handle)
    execution_device = getattr(pipe, "_execution_device", handle.device)
    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    prompt_embeds = None
    negative_prompt_embeds = None
    pooled_prompt_embeds = None
    negative_pooled_prompt_embeds = None
    encode_prompt = getattr(pipe, "encode_prompt", None)
    if callable(encode_prompt):
        encoded = encode_prompt(
            prompt=prompt,
            prompt_2=None,
            device=execution_device,
            num_images_per_prompt=1,
            do_classifier_free_guidance=guidance_scale > 1.0,
            negative_prompt=negative_prompt,
            negative_prompt_2=None,
        )
        (
            prompt_embeds,
            negative_prompt_embeds,
            pooled_prompt_embeds,
            negative_pooled_prompt_embeds,
        ) = encoded
        _offload_text_encoders(pipe=pipe)
        _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    result = pipe(
        prompt=None if prompt_embeds is not None else prompt,
        negative_prompt=None if negative_prompt_embeds is not None else negative_prompt,
        num_inference_steps=num_inference_steps,
        num_images_per_prompt=1,
        guidance_scale=guidance_scale,
        width=width,
        height=height,
        generator=generator,
        output_type="latent",
        prompt_embeds=prompt_embeds,
        negative_prompt_embeds=negative_prompt_embeds,
        pooled_prompt_embeds=pooled_prompt_embeds,
        negative_pooled_prompt_embeds=negative_pooled_prompt_embeds,
        return_dict=False,
    )
    _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    images = result[0] if isinstance(result, tuple) else result
    image = images[0] if isinstance(images, list) else images
    _offload_decode_stack(pipe=pipe, decoder=None)
    if isinstance(image, Image.Image):
        return image.convert("RGBA")
    return Image.fromarray(image, mode="RGBA")
