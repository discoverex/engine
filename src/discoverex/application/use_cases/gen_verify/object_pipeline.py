from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.adapters.outbound.models.sam_object_mask import SamObjectMaskExtractor
from discoverex.application.context import AppContextLike
from discoverex.models.types import FxRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

logger = get_logger("discoverex.generate.objects")

_DEFAULT_OBJECT_GENERATION_PROMPT = "isolated hidden object"
_DEFAULT_OBJECT_NEGATIVE = (
    "busy scene, environment, multiple objects, floor, wall, clutter, blurry, artifact"
)
_OBJECT_GENERATION_SIZE = 512
_PLACEMENT_OBJECT_SIZE = 100
_OBJECT_GENERATION_STEPS = 30
_OBJECT_GENERATION_GUIDANCE = 5.0


@dataclass(frozen=True)
class GeneratedObjectAsset:
    region_id: str
    candidate_ref: str
    object_ref: str
    object_mask_ref: str
    width: int
    height: int
    raw_alpha_mask_ref: str | None = None
    mask_source: str = "unknown"
    tight_bbox: tuple[int, int, int, int] | None = None


def generate_region_objects(
    *,
    context: AppContextLike,
    scene_dir: Path,
    regions: list[object],
    object_handle: ModelHandle,
    object_prompt: str,
    object_negative_prompt: str,
) -> dict[str, GeneratedObjectAsset]:
    masker = SamObjectMaskExtractor(
        device=context.runtime.model_runtime.device,
        dtype=context.runtime.model_runtime.dtype,
    )
    generated: dict[str, GeneratedObjectAsset] = {}
    total_regions = len(regions)
    object_prompts = resolve_object_prompts(object_prompt, total_regions=total_regions)
    try:
        for index, region in enumerate(regions, start=1):
            region_prompt = object_prompts[index - 1]
            width = _OBJECT_GENERATION_SIZE
            height = _OBJECT_GENERATION_SIZE
            output_prefix = (
                scene_dir / "layers" / "object-candidates" / f"{region.region_id}"
            )
            candidate_path = output_prefix.with_suffix(".candidate.png")
            started = perf_counter()
            emit_progress_event(
                stage="object_generation",
                status="started",
                region_id=region.region_id,
                index=index,
                total=total_regions,
                width=width,
                height=height,
            )
            prediction = context.object_generator_model.predict(
                object_handle,
                FxRequest(
                    mode="object_generation",
                    params={
                        "output_path": str(candidate_path),
                        "width": width,
                        "height": height,
                        "seed": context.runtime.model_runtime.seed,
                        "prompt": _object_generation_prompt(region_prompt),
                        "negative_prompt": object_negative_prompt
                        or _DEFAULT_OBJECT_NEGATIVE,
                        "num_inference_steps": _OBJECT_GENERATION_STEPS,
                        "guidance_scale": _OBJECT_GENERATION_GUIDANCE,
                    },
                ),
            )
            generated_ref = str(prediction.get("output_path") or candidate_path)
            masked = masker.extract(
                image_path=generated_ref,
                output_prefix=output_prefix,
            )
            placement_assets = _build_placement_assets(
                context=context,
                object_path=Path(str(masked["object"])),
                mask_path=Path(str(masked["mask"])),
                raw_alpha_path=Path(str(masked.get("raw_alpha_mask", masked["mask"]))),
            )
            generated[region.region_id] = GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=generated_ref,
                object_ref=str(placement_assets["object"]),
                object_mask_ref=str(placement_assets["mask"]),
                width=int(placement_assets["width"]),
                height=int(placement_assets["height"]),
                raw_alpha_mask_ref=str(masked.get("raw_alpha_mask", masked["mask"])),
                mask_source=str(masked.get("mask_source", "unknown")),
                tight_bbox=placement_assets.get("tight_bbox"),
            )
            emit_progress_event(
                stage="object_generation",
                status="completed",
                region_id=region.region_id,
                index=index,
                total=total_regions,
                candidate_image_ref=generated_ref,
                object_image_ref=str(placement_assets["object"]),
                object_mask_ref=str(placement_assets["mask"]),
            )
            logger.info(
                "object generation completed region=%s candidate=%s object=%s duration=%s",
                region.region_id,
                generated_ref,
                placement_assets["object"],
                format_seconds(started),
            )
    finally:
        masker.unload()
    return generated


def _object_generation_prompt(object_prompt: str) -> str:
    prompt = object_prompt.strip() or _DEFAULT_OBJECT_GENERATION_PROMPT
    return (
        f"{prompt}, isolated single object, centered composition, "
        "plain neutral backdrop, no environment, no floor"
    )


def resolve_object_prompts(object_prompt: str, *, total_regions: int) -> list[str]:
    prompts = _split_object_prompts(object_prompt)
    if total_regions <= 0:
        return []
    if not prompts:
        prompts = [_DEFAULT_OBJECT_GENERATION_PROMPT]
    if len(prompts) >= total_regions:
        return prompts[:total_regions]
    padded = list(prompts)
    padded.extend([prompts[-1]] * (total_regions - len(prompts)))
    return padded


def _split_object_prompts(object_prompt: str) -> list[str]:
    prompt = object_prompt.strip()
    if not prompt:
        return []
    if prompt.startswith("["):
        try:
            import json

            parsed = json.loads(prompt)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    separators = ("\n", "|", ";")
    for separator in separators:
        if separator in prompt:
            return [part.strip() for part in prompt.split(separator) if part.strip()]
    return [prompt]


def _round_up_to_multiple_of_8(value: int) -> int:
    return max(8, ((value + 7) // 8) * 8)


def _resize_object_assets(
    *,
    object_path: Path,
    mask_path: Path,
    size: int,
) -> dict[str, Any]:
    from PIL import Image  # type: ignore

    resized_object = object_path.with_suffix(".object.scaled.png")
    resized_mask = mask_path.with_suffix(".mask.scaled.png")
    with Image.open(object_path).convert("RGBA") as object_image, Image.open(
        mask_path
    ).convert("L") as mask_image:
        tight_bbox = mask_image.getbbox() or (0, 0, mask_image.width, mask_image.height)
        object_tight = object_image.crop(tight_bbox)
        mask_tight = mask_image.crop(tight_bbox)
        target_w, target_h = _fit_inside(
            width=object_tight.width,
            height=object_tight.height,
            max_side=size,
        )
        object_scaled = object_tight.resize((target_w, target_h), Image.LANCZOS)
        mask_scaled = mask_tight.resize((target_w, target_h), Image.NEAREST)
        object_canvas = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
        mask_canvas = Image.new("L", (size, size), color=0)
        paste_left = max(0, (size - target_w) // 2)
        paste_top = max(0, (size - target_h) // 2)
        object_canvas.paste(object_scaled, (paste_left, paste_top), object_scaled)
        mask_canvas.paste(mask_scaled, (paste_left, paste_top))
        object_canvas.save(resized_object)
        mask_canvas.save(resized_mask)
    return {
        "object": resized_object,
        "mask": resized_mask,
    }


def _build_placement_assets(
    *,
    context: AppContextLike,
    object_path: Path,
    mask_path: Path,
    raw_alpha_path: Path,
) -> dict[str, Any]:
    inpaint_mode = str(getattr(context.inpaint_model, "inpaint_mode", ""))
    if inpaint_mode == "layerdiffuse_hidden_object_v1":
        from PIL import Image  # type: ignore

        with Image.open(mask_path).convert("L") as mask_image:
            tight_bbox = mask_image.getbbox() or (0, 0, mask_image.width, mask_image.height)
        return {
            "object": object_path,
            "mask": mask_path,
            "raw_alpha_mask": raw_alpha_path,
            "width": max(1, tight_bbox[2] - tight_bbox[0]),
            "height": max(1, tight_bbox[3] - tight_bbox[1]),
            "tight_bbox": tight_bbox,
        }
    resized = _resize_object_assets(
        object_path=object_path,
        mask_path=mask_path,
        size=_PLACEMENT_OBJECT_SIZE,
    )
    return {
        "object": resized["object"],
        "mask": resized["mask"],
        "raw_alpha_mask": raw_alpha_path,
        "width": _PLACEMENT_OBJECT_SIZE,
        "height": _PLACEMENT_OBJECT_SIZE,
        "tight_bbox": None,
    }


def _fit_inside(*, width: int, height: int, max_side: int) -> tuple[int, int]:
    longest_side = max(1, width, height)
    scale = min(1.0, max_side / float(longest_side))
    return (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
