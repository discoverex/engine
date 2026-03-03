from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background
from discoverex.models.types import HiddenRegionRequest, InpaintRequest, ModelHandle


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
    hidden_handle: ModelHandle,
    inpaint_handle: ModelHandle,
) -> list[Region]:
    boxes = context.hidden_region_model.predict(
        hidden_handle,
        HiddenRegionRequest(
            image_ref=background.asset_ref,
            width=background.width,
            height=background.height,
        ),
    )
    regions = build_candidate_regions(boxes)

    inpainted_regions: list[Region] = []
    for region in regions:
        output_path = (
            Path(context.artifacts_root)
            / "_tmp"
            / "inpaint"
            / f"{region.region_id}-{uuid4().hex[:8]}.png"
        )
        details = context.inpaint_model.predict(
            inpaint_handle,
            InpaintRequest(
                image_ref=background.asset_ref,
                region_id=region.region_id,
                bbox=(
                    region.geometry.bbox.x,
                    region.geometry.bbox.y,
                    region.geometry.bbox.w,
                    region.geometry.bbox.h,
                ),
                output_path=str(output_path),
                composite_base_ref=background.asset_ref,
                generation_prompt="repair hidden object region naturally",
            ),
        )
        updated = region.model_copy(deep=True)
        updated.source = RegionSource.INPAINT
        updated.attributes.update(details)
        composited_ref = details.get("composited_image_ref")
        if isinstance(composited_ref, str) and composited_ref:
            background.metadata["inpaint_composited_ref"] = composited_ref
        patch_ref = details.get("patch_image_ref")
        if isinstance(patch_ref, str) and patch_ref:
            candidates = background.metadata.setdefault("inpaint_layer_candidates", [])
            if isinstance(candidates, list):
                candidates.append(
                    {
                        "region_id": region.region_id,
                        "patch_image_ref": patch_ref,
                        "bbox": {
                            "x": region.geometry.bbox.x,
                            "y": region.geometry.bbox.y,
                            "w": region.geometry.bbox.w,
                            "h": region.geometry.bbox.h,
                        },
                    }
                )
        inpainted_regions.append(updated)
    return inpainted_regions
