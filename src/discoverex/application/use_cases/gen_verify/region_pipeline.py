from __future__ import annotations

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
            ),
        )
        updated = region.model_copy(deep=True)
        updated.source = RegionSource.INPAINT
        updated.attributes.update(details)
        inpainted_regions.append(updated)
    return inpainted_regions
