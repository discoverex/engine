from __future__ import annotations

from typing import Any


def load_inpaint_pipe(*, current_pipe: Any | None, model_id: str, revision: str, handle: Any) -> Any:
    if current_pipe is not None:
        return current_pipe
    try:
        import torch  # type: ignore
        from diffusers import AutoPipelineForInpainting  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "diffusers inpainting pipeline import failed. "
            "Install compatible ml-gpu or ml-cpu dependencies."
        ) from exc
    torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
    pipe = AutoPipelineForInpainting.from_pretrained(
        model_id,
        revision=revision,
        torch_dtype=torch_dtype,
    )
    if hasattr(pipe, "set_progress_bar_config"):
        pipe.set_progress_bar_config(disable=False)
    return pipe.to(handle.device)


def build_full_mask(width: int, height: int) -> Any:
    from PIL import Image, ImageDraw  # type: ignore

    mask = Image.new("L", (width, height), color=0)
    ImageDraw.Draw(mask).rectangle((0, 0, width, height), fill=255)
    return mask


def resize_patch_to_long_side(patch: Any, target_long_side: int) -> tuple[Any, tuple[int, int]]:
    width, height = patch.size
    if width <= 0 or height <= 0:
        return patch.resize((target_long_side, target_long_side)), (
            target_long_side,
            target_long_side,
        )
    scale = float(target_long_side) / float(max(width, height))
    size = _coerce_size_to_multiple_of_8(
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return patch.resize(size), size


def normalize_generated_patch(generated_patch: Any, target_size: tuple[int, int]) -> Any:
    from PIL import Image  # type: ignore

    patch = generated_patch.convert("RGB")
    if patch.size == target_size:
        return patch
    return patch.resize(target_size, Image.Resampling.LANCZOS)


def extract_object_rgba(original_patch: Any, generated_patch: Any) -> tuple[Any, Any]:
    from PIL import ImageChops, ImageFilter, ImageOps  # type: ignore

    base = original_patch.convert("RGB")
    generated = normalize_generated_patch(generated_patch, base.size)
    diff = ImageChops.difference(base, generated)
    channels = diff.split()
    mask = channels[0]
    for channel in channels[1:]:
        mask = ImageChops.lighter(mask, channel)
    mask = ImageOps.autocontrast(mask)
    focus = _build_center_focus_mask(base.size)
    mask = ImageChops.multiply(mask, focus)
    mask = mask.point(_threshold_diff_mask)
    mask = mask.filter(ImageFilter.MaxFilter(5))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.0))
    mask = mask.point(_scale_mask_alpha)
    object_image = generated.convert("RGBA")
    object_image.putalpha(mask)
    return object_image, mask


def has_meaningful_mask(mask: Any) -> bool:
    if mask.getbbox() is None:
        return False
    histogram = mask.histogram()
    nonzero = sum(histogram[1:])
    weighted_alpha = sum(level * count for level, count in enumerate(histogram))
    return nonzero >= 9 and weighted_alpha >= 255 * 6


def _scale_mask_alpha(value: int) -> int:
    if value < 24:
        return 0
    scaled = (value - 24) * 6
    return max(0, min(255, scaled))


def _threshold_diff_mask(value: int) -> int:
    return 255 if value >= 40 else 0


def _build_center_focus_mask(size: tuple[int, int]) -> Any:
    from PIL import Image, ImageDraw, ImageFilter  # type: ignore

    width, height = size
    margin_x = max(1, int(width * 0.15))
    margin_y = max(1, int(height * 0.15))
    mask = Image.new("L", size, color=0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        (margin_x, margin_y, width - margin_x, height - margin_y),
        fill=255,
    )
    return mask.filter(ImageFilter.GaussianBlur(radius=max(1.0, min(size) * 0.04)))


def _coerce_size_to_multiple_of_8(width: int, height: int) -> tuple[int, int]:
    return (_round_up_to_multiple_of_8(width), _round_up_to_multiple_of_8(height))


def _round_up_to_multiple_of_8(value: int) -> int:
    return max(8, ((value + 7) // 8) * 8)
