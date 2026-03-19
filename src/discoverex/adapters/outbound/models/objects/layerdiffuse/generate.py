from __future__ import annotations

from typing import Any

from PIL import Image  # type: ignore


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
) -> Any:
    import torch  # type: ignore

    pipe = model._load_pipeline(handle)
    execution_device = getattr(pipe, "_execution_device", handle.device)
    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        width=width,
        height=height,
        generator=generator,
        output_type="latent",
    )
    latents = result.images
    decoder = model._load_transparent_decoder(handle)
    vae = pipe.vae.to(device=execution_device, dtype=pipe.vae.dtype)
    decoder = decoder.to(device=execution_device, dtype=pipe.vae.dtype)
    latents = latents.to(device=execution_device, dtype=pipe.vae.dtype) / vae.config.scaling_factor
    rgba_images, _ = decoder(vae, latents)
    return Image.fromarray(rgba_images[0], mode="RGBA")
