from __future__ import annotations

from typing import Any


def generate_base_image(
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

    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    pipe = model._load_base_pipe(handle)
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        width=width,
        height=height,
        generator=generator,
        clean_caption=False,
    )
    images = getattr(result, "images", None)
    if not images:
        raise RuntimeError("pixart pipeline returned no images")
    return images[0]


def upscale_canvas(*, image: Any, width: int, height: int, canvas_scale_factor: float) -> Any:
    from PIL import Image  # type: ignore

    if width <= 0 or height <= 0:
        width = max(1, int(round(image.width * canvas_scale_factor)))
        height = max(1, int(round(image.height * canvas_scale_factor)))
    return image.resize((width, height), Image.Resampling.LANCZOS)
