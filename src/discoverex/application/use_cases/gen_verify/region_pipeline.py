from __future__ import annotations

from math import hypot
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background
from discoverex.models.types import InpaintRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from .object_pipeline import GeneratedObjectAsset
from .object_pipeline import resolve_object_prompts
from .region_prompts import (
    bbox_payload,
    bbox_tuple,
    build_prompt_record,
    record_layer_candidate,
)
from .runtime_metrics import track_stage_vram
from .types import RegionPromptRecord

_DEFAULT_OBJECT_GENERATION_PROMPT = "repair hidden object region naturally"
_MIN_REGION_CENTER_DISTANCE_RATIO = 0.85
_MAX_REGION_IOU = 0.12
logger = get_logger("discoverex.generate.regions")


def build_candidate_regions(
    boxes: list[tuple[float, float, float, float]],
) -> list[Region]:
    regions: list[Region] = []
    accepted_boxes: list[tuple[float, float, float, float]] = []
    for bbox in boxes:
        if not _is_region_sufficiently_separated(bbox, accepted_boxes):
            continue
        accepted_boxes.append(bbox)
    for idx, bbox in enumerate(accepted_boxes):
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
        region_prompt = object_prompts[index - 1]
        region_started = perf_counter()
        output_path = (
            scene_dir
            / "assets"
            / "patches"
            / f"{region.region_id}-{uuid4().hex[:8]}.png"
        )
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
            _object_inpaint_vram_stage(index=index, region_id=region.region_id),
        ):
            object_asset = generated_objects.get(region.region_id)
            if object_asset is None:
                raise ValueError(f"missing generated object for region {region.region_id}")
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
            "candidate_image_ref": details.get("candidate_image_ref") or object_asset.candidate_ref,
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
        prompt_records.append(
            build_prompt_record(
                region=updated,
                object_prompt=region_prompt,
                object_negative_prompt=object_negative_prompt,
                generation_prompt=generation_prompt,
                details=details,
            )
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
        inpainted_regions.append(updated)
    return inpainted_regions, prompt_records


def _object_inpaint_vram_stage(*, index: int, region_id: str) -> str:
    safe_region_id = region_id.replace("/", "_")
    return f"object_inpaint_{index:02d}_{safe_region_id}"


def _is_region_sufficiently_separated(
    candidate: tuple[float, float, float, float],
    accepted: list[tuple[float, float, float, float]],
) -> bool:
    for existing in accepted:
        if _bbox_iou(candidate, existing) > _MAX_REGION_IOU:
            return False
        min_distance = max(
            min(candidate[2], candidate[3]),
            min(existing[2], existing[3]),
        ) * _MIN_REGION_CENTER_DISTANCE_RATIO
        if _bbox_center_distance(candidate, existing) < min_distance:
            return False
    return True


def _bbox_center_distance(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_center = (first[0] + first[2] / 2.0, first[1] + first[3] / 2.0)
    second_center = (second[0] + second[2] / 2.0, second[1] + second[3] / 2.0)
    return hypot(first_center[0] - second_center[0], first_center[1] - second_center[1])


def _bbox_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_left, first_top, first_w, first_h = first
    second_left, second_top, second_w, second_h = second
    left = max(first_left, second_left)
    top = max(first_top, second_top)
    right = min(first_left + first_w, second_left + second_w)
    bottom = min(first_top + first_h, second_top + second_h)
    inter_w = max(0.0, right - left)
    inter_h = max(0.0, bottom - top)
    intersection = inter_w * inter_h
    if intersection <= 0.0:
        return 0.0
    first_area = max(0.0, first_w) * max(0.0, first_h)
    second_area = max(0.0, second_w) * max(0.0, second_h)
    union = first_area + second_area - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union
