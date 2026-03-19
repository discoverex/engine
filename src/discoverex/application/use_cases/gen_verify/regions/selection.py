from __future__ import annotations

from math import hypot
from uuid import uuid4

from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource

_MIN_REGION_CENTER_DISTANCE_RATIO = 0.85
_MAX_REGION_IOU = 0.12


def build_candidate_regions(
    boxes: list[tuple[float, float, float, float]],
) -> list[Region]:
    regions: list[Region] = []
    accepted_boxes: list[tuple[float, float, float, float]] = []
    for bbox in boxes:
        if not is_region_sufficiently_separated(bbox, accepted_boxes):
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


def is_region_sufficiently_separated(
    candidate: tuple[float, float, float, float],
    accepted: list[tuple[float, float, float, float]],
) -> bool:
    for existing in accepted:
        if bbox_iou(candidate, existing) > _MAX_REGION_IOU:
            return False
        min_distance = (
            max(min(candidate[2], candidate[3]), min(existing[2], existing[3]))
            * _MIN_REGION_CENTER_DISTANCE_RATIO
        )
        if bbox_center_distance(candidate, existing) < min_distance:
            return False
    return True


def bbox_center_distance(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_center = (first[0] + first[2] / 2.0, first[1] + first[3] / 2.0)
    second_center = (second[0] + second[2] / 2.0, second[1] + second[3] / 2.0)
    return hypot(first_center[0] - second_center[0], first_center[1] - second_center[1])


def bbox_iou(
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
