from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from PIL import Image  # type: ignore

def _stdout_debug(message: str) -> None:
    print(f"[discoverex-debug] {message}", flush=True)


@dataclass(frozen=True)
class LayerDiffuseGenerationResult:
    preview_rgb: Image.Image
    transparent_rgba: Image.Image
    alpha_mask: Image.Image
    visualization_rgb: Image.Image

    @property
    def mode(self) -> str:
        return self.transparent_rgba.mode


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


def _decode_latents_to_results(*, model: Any, pipe: Any, latents: Any) -> list[LayerDiffuseGenerationResult]:
    transparent_decoder = getattr(model, "_transparent_decoder", None)
    base_vae = getattr(pipe, "_layerdiffuse_base_vae", None)
    if transparent_decoder is not None and base_vae is not None:
        decode_device = getattr(latents, "device", getattr(pipe, "_execution_device", "cpu"))
        decode_dtype = getattr(base_vae, "dtype", getattr(latents, "dtype", None))
        try:
            base_vae.to(device=decode_device, dtype=decode_dtype)
        except Exception:
            pass
        try:
            transparent_decoder.to(device=decode_device, dtype=decode_dtype)
        except Exception:
            pass
        latents_for_decode = latents / base_vae.config.scaling_factor
        rgba_images, visualization_images = transparent_decoder(base_vae, latents_for_decode)
        preview_decoded = base_vae.decode(latents_for_decode).sample
        preview_images = _to_rgba_images(preview_decoded)
        results: list[LayerDiffuseGenerationResult] = []
        for preview_image, rgba_image, visualization_image in zip(
            preview_images,
            rgba_images,
            visualization_images,
            strict=True,
        ):
            transparent_rgba = Image.fromarray(rgba_image, mode="RGBA")
            visualization_rgb = Image.fromarray(visualization_image, mode="RGB")
            results.append(
                LayerDiffuseGenerationResult(
                    preview_rgb=preview_image.convert("RGB"),
                    transparent_rgba=transparent_rgba,
                    alpha_mask=transparent_rgba.getchannel("A"),
                    visualization_rgb=visualization_rgb,
                )
            )
        return results
    decoded = pipe.vae.decode(latents, return_dict=False)[0]
    images = _to_rgba_images(decoded)
    results: list[LayerDiffuseGenerationResult] = []
    for image in images:
        rgba = image.convert("RGBA")
        results.append(
            LayerDiffuseGenerationResult(
                preview_rgb=image.convert("RGB"),
                transparent_rgba=rgba,
                alpha_mask=rgba.getchannel("A"),
                visualization_rgb=image.convert("RGB"),
            )
        )
    return results


def _coerce_generation_result(image: Any) -> LayerDiffuseGenerationResult:
    if isinstance(image, LayerDiffuseGenerationResult):
        return image
    rgba = _to_rgba_image(image)
    return LayerDiffuseGenerationResult(
        preview_rgb=rgba.convert("RGB"),
        transparent_rgba=rgba,
        alpha_mask=rgba.getchannel("A"),
        visualization_rgb=rgba.convert("RGB"),
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
    call_signature = inspect.signature(pipe.__call__)
    pipe_kwargs: dict[str, Any] = {
        "prompt": prompts,
        "negative_prompt": negative_prompts,
        "num_inference_steps": num_inference_steps,
        "num_images_per_prompt": 1,
        "guidance_scale": guidance_scale,
        "width": width,
        "height": height,
        "generator": generator,
        "output_type": "latent",
        "return_dict": False,
    }
    try:
        result = pipe(**pipe_kwargs)
    except Exception as exc:
        _stdout_debug(
            "layerdiffuse_pipe_exception "
            f"error={exc!r} "
            f"generator_type={type(generator).__name__ if generator is not None else 'None'} "
            f"width={width} height={height} steps={num_inference_steps} guidance={guidance_scale}"
        )
        raise
    _raise_if_vram_limit_exceeded(limit_gb=max_vram_gb)
    latents = result[0] if isinstance(result, tuple) else result
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
) -> LayerDiffuseGenerationResult:
    import torch  # type: ignore

    pipe = model._load_pipeline(handle)
    execution_device = getattr(handle, "device", None) or getattr(pipe, "_execution_device", "cpu")
    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    latents = _sample_latents(
        pipe=pipe,
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
    images = _decode_latents_to_results(model=model, pipe=pipe, latents=latents)
    image = images[0]
    return _coerce_generation_result(image)


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
) -> list[LayerDiffuseGenerationResult]:
    import torch  # type: ignore

    if not prompts:
        return []
    if len(prompts) != len(negative_prompts):
        raise ValueError("prompts and negative_prompts must have the same length")
    pipe = model._load_pipeline(handle)
    execution_device = getattr(handle, "device", None) or getattr(pipe, "_execution_device", "cpu")
    generator = None if seed is None else torch.Generator(device="cpu").manual_seed(seed)
    latents = _sample_latents(
        pipe=pipe,
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
    images = _decode_latents_to_results(model=model, pipe=pipe, latents=latents)
    return images
