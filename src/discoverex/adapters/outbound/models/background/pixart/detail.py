from __future__ import annotations

from typing import Any


def reconstruct_details(
    *,
    model: Any,
    handle: Any,
    image: Any,
    prompt: str,
    negative_prompt: str,
    seed: int | None,
    num_inference_steps: int,
    guidance_scale: float,
    strength: float,
) -> Any:
    return image if not model.detail_model_id else refine_tiled(
        model=model,
        handle=handle,
        image=image,
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        strength=strength,
    )


def refine_tiled(*, model: Any, handle: Any, image: Any, prompt: str, negative_prompt: str, seed: int | None, num_inference_steps: int, guidance_scale: float, strength: float) -> Any:
    import numpy as np
    import torch  # type: ignore
    from PIL import Image  # type: ignore

    pipe = model._load_detail_pipe(handle)
    tile_size = max(64, int(model.tile_size))
    overlap = max(0, min(int(model.tile_overlap), tile_size // 2))
    step = max(1, tile_size - overlap)
    canvas = np.zeros((image.height, image.width, 3), dtype=np.float32)
    weights = np.zeros((image.height, image.width, 1), dtype=np.float32)
    tile_index = 0
    for top in tile_positions(image.height, tile_size, step):
        for left in tile_positions(image.width, tile_size, step):
            tile = image.crop((left, top, left + tile_size, top + tile_size))
            generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed + tile_index)
            result = pipe(prompt=prompt, negative_prompt=negative_prompt, image=tile, strength=strength, num_inference_steps=num_inference_steps, guidance_scale=guidance_scale, generator=generator)
            images = getattr(result, "images", None)
            tile_arr = np.asarray((images[0] if images else tile).convert("RGB"), dtype=np.float32)
            weight = build_weight_map(width=tile_arr.shape[1], height=tile_arr.shape[0], feather=max(8, overlap // 2))
            bottom = min(image.height, top + tile_arr.shape[0])
            right = min(image.width, left + tile_arr.shape[1])
            canvas[top:bottom, left:right, :] += tile_arr[: bottom - top, : right - left, :] * weight[: bottom - top, : right - left, :]
            weights[top:bottom, left:right, :] += weight[: bottom - top, : right - left, :]
            tile_index += 1
    merged = np.clip(canvas / np.maximum(weights, 1e-6), 0.0, 255.0).astype("uint8")
    return Image.fromarray(merged, mode="RGB")


def tile_positions(length: int, tile_size: int, step: int) -> list[int]:
    if length <= tile_size:
        return [0]
    positions = list(range(0, max(1, length - tile_size + 1), step))
    last = max(0, length - tile_size)
    if not positions or positions[-1] != last:
        positions.append(last)
    return positions


def build_weight_map(*, width: int, height: int, feather: int) -> Any:
    import numpy as np

    feather = max(1, min(feather, width // 2, height // 2))
    x = np.ones(width, dtype=np.float32)
    y = np.ones(height, dtype=np.float32)
    ramp_x = np.linspace(0.0, 1.0, feather, dtype=np.float32)
    ramp_y = np.linspace(0.0, 1.0, feather, dtype=np.float32)
    x[:feather], x[-feather:], y[:feather], y[-feather:] = ramp_x, ramp_x[::-1], ramp_y, ramp_y[::-1]
    return np.outer(y, x)[:, :, None]
