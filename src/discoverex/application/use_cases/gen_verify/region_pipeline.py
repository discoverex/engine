from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background
from discoverex.models.types import InpaintRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from .region_prompts import (
    bbox_payload,
    bbox_tuple,
    build_prompt_record,
    record_layer_candidate,
)
from .runtime_metrics import track_stage_vram
from .types import RegionPromptRecord

_DEFAULT_OBJECT_GENERATION_PROMPT = "repair hidden object region naturally"
logger = get_logger("discoverex.generate.regions")


def build_candidate_regions(
    boxes: list[tuple[float, float, float, float]],
) -> list[Region]:
    regions: list[Region] = []
    for idx, bbox in enumerate(boxes):
        role = RegionRole.ANSWER if idx == 0 else RegionRole.CANDIDATE
        regions.append(
            Region(
                region_id=f"r-{uuid4().hex[:10]}",
                geometry=Geometry(
                    type="bbox",
                    bbox=BBox(x=bbox[0], y=bbox[1], w=bbox[2], h=bbox[3]),
                ),
                role=role,
                source=RegionSource.CANDIDATE_MODEL,
                attributes={"proposal_rank": idx + 1},
                version=1,
            )
        )
    return regions


def generate_regions(
    context: AppContextLike,
    background: Background,
    scene_dir: Path,
    regions: list[Region],
    inpaint_handle: ModelHandle,
    object_prompt: str = "",
    object_negative_prompt: str = "",
) -> tuple[list[Region], list[RegionPromptRecord]]:
    inpainted_regions: list[Region] = []
    prompt_records: list[RegionPromptRecord] = []
    total_regions = len(regions)
    for index, region in enumerate(regions, start=1):
        region_started = perf_counter()
        output_path = (
            scene_dir
            / "layers"
            / "inpaint"
            / f"{region.region_id}-{uuid4().hex[:8]}.png"
        )
        generation_prompt = object_prompt or _DEFAULT_OBJECT_GENERATION_PROMPT
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
            _object_inpaint_vram_stage(index=index, region_id=region.region_id),
        ):
            details = context.inpaint_model.predict(
                inpaint_handle,
                InpaintRequest(
                    image_ref=background.asset_ref,
                    region_id=region.region_id,
                    bbox=bbox_tuple(region),
                    output_path=str(output_path),
                    composite_base_ref=background.asset_ref,
                    prompt=object_prompt,
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
        object_ref = details.get("object_image_ref")
        object_mask_ref = details.get("object_mask_ref")
        patch_ref = details.get("patch_image_ref")
        record_layer_candidate(
            background=background,
            region=updated,
            object_ref=object_ref,
            object_mask_ref=object_mask_ref,
            patch_ref=patch_ref,
        )
        prompt_records.append(
            build_prompt_record(
                region=updated,
                object_prompt=object_prompt,
                object_negative_prompt=object_negative_prompt,
                generation_prompt=generation_prompt,
                details=details,
            )
        )
        logger.info(
            "object inpaint completed region=%s patch=%s object=%s composited=%s duration=%s",
            region.region_id,
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
        inpainted_regions.append(updated)
    return inpainted_regions, prompt_records


def _object_inpaint_vram_stage(*, index: int, region_id: str) -> str:
    safe_region_id = region_id.replace("/", "_")
    return f"object_inpaint_{index:02d}_{safe_region_id}"
