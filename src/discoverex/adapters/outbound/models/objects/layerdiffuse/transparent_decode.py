from __future__ import annotations

# mypy: ignore-errors
from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class TransparentDecodeResult:
    preview_rgb: Image.Image
    transparent_rgba: Image.Image
    alpha_mask: Image.Image
    visualization_rgb: Image.Image


class LayerDiffuseTransparentDecoder:
    def to(self, device: Any) -> "LayerDiffuseTransparentDecoder":
        _ = device
        return self

    def decode(self, *, transparent_vae: Any, latents: Any) -> list[TransparentDecodeResult]:
        preview_tensor = transparent_vae.decode_preview(latents).sample
        preview_images = _tensor_batch_to_rgb(preview_tensor)
        transparent_tensor = transparent_vae.decode(latents).sample
        transparent_images = _tensor_batch_to_rgba(transparent_tensor)
        results: list[TransparentDecodeResult] = []
        for preview_image, transparent_image in zip(
            preview_images,
            transparent_images,
            strict=True,
        ):
            results.append(
                TransparentDecodeResult(
                    preview_rgb=preview_image,
                    transparent_rgba=transparent_image,
                    alpha_mask=transparent_image.getchannel("A"),
                    visualization_rgb=_build_visualization(transparent_image),
                )
            )
        return results


def _tensor_batch_to_rgb(batch: Any) -> list[Image.Image]:
    import numpy as np  # type: ignore

    tensor = batch.detach().float().cpu()
    if tensor.ndim == 3:
        tensor = tensor.unsqueeze(0)
    images: list[Image.Image] = []
    for image_tensor in tensor:
        image_tensor = image_tensor.clamp(-1.0, 1.0)
        image_tensor = ((image_tensor / 2.0) + 0.5).clamp(0.0, 1.0)
        array = image_tensor.permute(1, 2, 0).numpy()
        rgb = (array * 255.0).round().astype(np.uint8)
        images.append(Image.fromarray(rgb, mode="RGB"))
    return images


def _tensor_batch_to_rgba(batch: Any) -> list[Image.Image]:
    import numpy as np  # type: ignore

    tensor = batch.detach().float().cpu()
    if tensor.ndim == 3:
        tensor = tensor.unsqueeze(0)
    images: list[Image.Image] = []
    for image_tensor in tensor:
        image_tensor = image_tensor.clamp(-1.0, 1.0)
        image_tensor = ((image_tensor / 2.0) + 0.5).clamp(0.0, 1.0)
        array = image_tensor.permute(1, 2, 0).numpy()
        rgba = (array * 255.0).round().astype(np.uint8)
        images.append(Image.fromarray(rgba, mode="RGBA"))
    return images


def _build_visualization(transparent_image: Image.Image) -> Image.Image:
    from PIL import ImageChops

    width, height = transparent_image.size
    tile = 32
    board = Image.new("RGB", (width, height), color=(200, 200, 200))
    alt = Image.new("RGB", (tile, tile), color=(160, 160, 160))
    for top in range(0, height, tile):
        for left in range(0, width, tile):
            if ((left // tile) + (top // tile)) % 2 == 0:
                board.paste(alt, (left, top))
    foreground = transparent_image.convert("RGBA")
    composed = board.convert("RGBA")
    composed.alpha_composite(foreground)
    return ImageChops.duplicate(composed).convert("RGB")
