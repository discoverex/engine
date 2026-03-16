from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

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


@dataclass(frozen=True)
class GeneratedObjectAsset:
    region_id: str
    candidate_ref: str
    object_ref: str
    object_mask_ref: str
    width: int
    height: int


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
    try:
        for index, region in enumerate(regions, start=1):
            bbox = region.geometry.bbox
            width = _round_up_to_multiple_of_8(max(64, int(round(bbox.w))))
            height = _round_up_to_multiple_of_8(max(64, int(round(bbox.h))))
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
                        "prompt": _object_generation_prompt(object_prompt),
                        "negative_prompt": object_negative_prompt
                        or _DEFAULT_OBJECT_NEGATIVE,
                    },
                ),
            )
            generated_ref = str(prediction.get("output_path") or candidate_path)
            masked = masker.extract(
                image_path=generated_ref,
                output_prefix=output_prefix,
            )
            generated[region.region_id] = GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=generated_ref,
                object_ref=str(masked["object"]),
                object_mask_ref=str(masked["mask"]),
                width=width,
                height=height,
            )
            emit_progress_event(
                stage="object_generation",
                status="completed",
                region_id=region.region_id,
                index=index,
                total=total_regions,
                candidate_image_ref=generated_ref,
                object_image_ref=str(masked["object"]),
                object_mask_ref=str(masked["mask"]),
            )
            logger.info(
                "object generation completed region=%s candidate=%s object=%s duration=%s",
                region.region_id,
                generated_ref,
                masked["object"],
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


def _round_up_to_multiple_of_8(value: int) -> int:
    return max(8, ((value + 7) // 8) * 8)
