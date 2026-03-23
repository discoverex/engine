from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from discoverex.application.context import AppContextLike

from .types import PlacementAssets

_PLACEMENT_OBJECT_SIZE = 100


def relocate_mask_assets(
    *,
    scene_dir: Path,
    masked: dict[str, str | Path],
) -> tuple[Path, Path]:
    masks_dir = scene_dir / "assets" / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)
    mask_path = move_if_needed(Path(str(masked["mask"])), masks_dir)
    raw_alpha_path = move_if_needed(
        Path(str(masked.get("raw_alpha_mask", masked["mask"]))),
        masks_dir,
    )
    return mask_path, raw_alpha_path


def move_if_needed(source: Path, target_dir: Path) -> Path:
    target = target_dir / source.name
    if source.resolve() == target.resolve():
        return source
    shutil.move(str(source), str(target))
    return target


def resize_object_assets(
    *,
    object_path: Path,
    size: int,
) -> tuple[Path, Path]:
    resized_object = object_path.with_suffix(".object.scaled.png")
    resized_mask = object_path.with_suffix(".mask.scaled.png")
    with Image.open(object_path).convert("RGBA") as object_image:
        mask_image = object_image.getchannel("A")
        tight_bbox = mask_image.getbbox() or (0, 0, mask_image.width, mask_image.height)
        object_tight = object_image.crop(tight_bbox)
        mask_tight = mask_image.crop(tight_bbox)
        target_w, target_h = fit_inside(
            width=object_tight.width,
            height=object_tight.height,
            max_side=size,
        )
        object_scaled = object_tight.resize(
            (target_w, target_h),
            Image.Resampling.LANCZOS,
        )
        mask_scaled = mask_tight.resize(
            (target_w, target_h),
            Image.Resampling.NEAREST,
        )
        object_canvas = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
        mask_canvas = Image.new("L", (size, size), color=0)
        paste_left = max(0, (size - target_w) // 2)
        paste_top = max(0, (size - target_h) // 2)
        object_canvas.paste(object_scaled, (paste_left, paste_top), object_scaled)
        mask_canvas.paste(mask_scaled, (paste_left, paste_top))
        object_canvas.save(resized_object)
        mask_canvas.save(resized_mask)
    return resized_object, resized_mask


def build_placement_assets(
    *,
    context: AppContextLike,
    object_path: Path,
    mask_path: Path,
    raw_alpha_path: Path,
) -> PlacementAssets:
    inpaint_mode = str(getattr(context.inpaint_model, "inpaint_mode", ""))
    if inpaint_mode == "layerdiffuse_hidden_object_v1":
        with Image.open(object_path).convert("RGBA") as object_image:
            mask_image = object_image.getchannel("A")
            tight_bbox = mask_image.getbbox() or (
                0,
                0,
                mask_image.width,
                mask_image.height,
            )
        return PlacementAssets(
            object_path=object_path,
            mask_path=mask_path,
            raw_alpha_path=raw_alpha_path,
            width=max(1, tight_bbox[2] - tight_bbox[0]),
            height=max(1, tight_bbox[3] - tight_bbox[1]),
            tight_bbox=tight_bbox,
        )
    resized_object, resized_mask = resize_object_assets(
        object_path=object_path,
        size=_PLACEMENT_OBJECT_SIZE,
    )
    return PlacementAssets(
        object_path=resized_object,
        mask_path=resized_mask,
        raw_alpha_path=raw_alpha_path,
        width=_PLACEMENT_OBJECT_SIZE,
        height=_PLACEMENT_OBJECT_SIZE,
    )


def fit_inside(*, width: int, height: int, max_side: int) -> tuple[int, int]:
    longest_side = max(1, width, height)
    scale = min(1.0, max_side / float(longest_side))
    return (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
