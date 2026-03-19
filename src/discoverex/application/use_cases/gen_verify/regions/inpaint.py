from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.domain.region import BBox, Region, RegionSource
from discoverex.domain.scene import Background
from discoverex.models.types import InpaintRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from ..object_pipeline import GeneratedObjectAsset, resolve_object_prompts
from ..region_prompts import (
    bbox_payload,
    bbox_tuple,
    build_prompt_record,
    record_layer_candidate,
)
from ..runtime_metrics import track_stage_vram
from ..types import RegionPromptRecord

_DEFAULT_OBJECT_GENERATION_PROMPT = "repair hidden object region naturally"
logger = get_logger("discoverex.generate.regions")


def generate_regions(
    context: AppContextLike,
    background: Background,
    scene_dir: Path,
    regions: list[Region],
    generated_objects: dict[str, GeneratedObjectAsset],
    inpaint_handle: ModelHandle,
    object_prompt: str = "",
    object_negative_prompt: str = "",
) -> tuple[list[Region], list[RegionPromptRecord]]:
    inpainted_regions: list[Region] = []
    prompt_records: list[RegionPromptRecord] = []
    total_regions = len(regions)
    object_prompts = resolve_object_prompts(object_prompt, total_regions=total_regions)
    current_composite_ref = str(
        background.metadata.get("inpaint_composited_ref") or background.asset_ref
    )
    for index, region in enumerate(regions, start=1):
        current_composite_ref, updated, prompt_record = _generate_single_region(
            context=context,
            background=background,
            scene_dir=scene_dir,
            region=region,
            index=index,
            total_regions=total_regions,
            object_asset=generated_objects.get(region.region_id),
            inpaint_handle=inpaint_handle,
            region_prompt=object_prompts[index - 1],
            object_negative_prompt=object_negative_prompt,
            current_composite_ref=current_composite_ref,
        )
        inpainted_regions.append(updated)
        prompt_records.append(prompt_record)
    return inpainted_regions, prompt_records


def object_inpaint_vram_stage(*, index: int, region_id: str) -> str:
    safe_region_id = region_id.replace("/", "_")
    return f"object_inpaint_{index:02d}_{safe_region_id}"


def _generate_single_region(
    *,
    context: AppContextLike,
    background: Background,
    scene_dir: Path,
    region: Region,
    index: int,
    total_regions: int,
    object_asset: GeneratedObjectAsset | None,
    inpaint_handle: ModelHandle,
    region_prompt: str,
    object_negative_prompt: str,
    current_composite_ref: str,
) -> tuple[str, Region, RegionPromptRecord]:
    if object_asset is None:
        raise ValueError(f"missing generated object for region {region.region_id}")
    region_started = perf_counter()
    output_path = scene_dir / "assets" / "patches" / f"{region.region_id}-{uuid4().hex[:8]}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generation_prompt = region_prompt or _DEFAULT_OBJECT_GENERATION_PROMPT
    logger.info(
        "object inpaint started region=%s index=%d/%d bbox=(%.1f,%.1f,%.1f,%.1f)",
        region.region_id,
        index,
        total_regions,
        region.geometry.bbox.x,
        region.geometry.bbox.y,
        region.geometry.bbox.w,
        region.geometry.bbox.h,
    )
    emit_progress_event(
        stage="object_inpaint",
        status="started",
        region_id=region.region_id,
        index=index,
        total=total_regions,
        bbox=bbox_payload(region),
    )
    with track_stage_vram(
        context,
        object_inpaint_vram_stage(index=index, region_id=region.region_id),
    ):
        details = context.inpaint_model.predict(
            inpaint_handle,
            InpaintRequest(
                image_ref=current_composite_ref,
                region_id=region.region_id,
                bbox=bbox_tuple(region),
                object_image_ref=object_asset.object_ref,
                object_mask_ref=object_asset.object_mask_ref,
                object_candidate_ref=object_asset.candidate_ref,
                output_path=str(output_path),
                composite_base_ref=current_composite_ref,
                prompt=region_prompt,
                negative_prompt=object_negative_prompt,
                generation_prompt=generation_prompt,
            ),
        )
    updated = region.model_copy(deep=True)
    updated.source = RegionSource.INPAINT
    selected_bbox = details.get("selected_bbox")
    if isinstance(selected_bbox, dict):
        try:
            updated.geometry.bbox = BBox(
                x=float(selected_bbox["x"]),
                y=float(selected_bbox["y"]),
                w=float(selected_bbox["w"]),
                h=float(selected_bbox["h"]),
            )
        except (KeyError, TypeError, ValueError):
            pass
    updated.attributes.update(details)
    composited_ref = details.get("composited_image_ref")
    if isinstance(composited_ref, str) and composited_ref:
        background.metadata["inpaint_composited_ref"] = composited_ref
        current_composite_ref = composited_ref
    object_ref = details.get("object_image_ref") or object_asset.object_ref
    object_mask_ref = details.get("object_mask_ref") or object_asset.object_mask_ref
    patch_ref = details.get("patch_image_ref") or object_asset.object_ref
    details = {
        **details,
        "candidate_image_ref": details.get("candidate_image_ref")
        or object_asset.candidate_ref,
        "object_image_ref": object_ref,
        "object_mask_ref": object_mask_ref,
        "patch_image_ref": patch_ref,
    }
    record_layer_candidate(
        background=background,
        region=updated,
        candidate_ref=details.get("candidate_image_ref"),
        object_ref=object_ref,
        object_mask_ref=object_mask_ref,
        patch_ref=patch_ref,
    )
    prompt_record = build_prompt_record(
        region=updated,
        object_prompt=region_prompt,
        object_negative_prompt=object_negative_prompt,
        generation_prompt=generation_prompt,
        details=details,
    )
    logger.info(
        "object inpaint completed region=%s prompt=%s patch=%s object=%s composited=%s duration=%s",
        region.region_id,
        region_prompt,
        details.get("patch_image_ref"),
        details.get("object_image_ref"),
        details.get("composited_image_ref"),
        format_seconds(region_started),
    )
    emit_progress_event(
        stage="object_inpaint",
        status="completed",
        region_id=region.region_id,
        index=index,
        total=total_regions,
        patch_image_ref=details.get("patch_image_ref"),
        object_image_ref=details.get("object_image_ref"),
        composited_image_ref=details.get("composited_image_ref"),
    )
    return current_composite_ref, updated, prompt_record
