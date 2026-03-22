from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource


def has_fixed_replay_inputs(args: dict[str, Any]) -> bool:
    return bool(
        str(args.get("object_image_ref", "") or "").strip()
        and str(args.get("object_mask_ref", "") or "").strip()
        and isinstance(args.get("bbox"), dict)
    )


def build_fixed_replay_inputs(
    *,
    args: dict[str, Any],
    object_prompt: str,
    object_negative_prompt: str,
    object_model_id: str = "",
    object_sampler: str = "",
    object_steps: int = 0,
    object_guidance_scale: float = 0.0,
    object_seed: int | None = None,
) -> tuple[list[Region], dict[str, GeneratedObjectAsset]]:
    bbox = args.get("bbox")
    if not isinstance(bbox, dict):
        raise ValueError("fixed replay requires args.bbox as an object")
    object_ref = str(args.get("object_image_ref", "") or "").strip()
    object_mask_ref = str(args.get("object_mask_ref", "") or "").strip()
    if not object_ref or not object_mask_ref:
        raise ValueError("fixed replay requires object_image_ref and object_mask_ref")
    raw_alpha_ref = str(args.get("raw_alpha_mask_ref", "") or "").strip() or object_mask_ref
    candidate_ref = str(args.get("object_candidate_ref", "") or "").strip() or object_ref
    region_id = str(args.get("region_id", "") or "").strip() or "replay-region-001"
    width = int(round(float(bbox["w"])))
    height = int(round(float(bbox["h"])))
    region = Region(
        region_id=region_id,
        geometry=Geometry(
            type="bbox",
            bbox=BBox(
                x=float(bbox["x"]),
                y=float(bbox["y"]),
                w=float(bbox["w"]),
                h=float(bbox["h"]),
            ),
        ),
        role=RegionRole.ANSWER,
        source=RegionSource.MANUAL,
        version=1,
    )
    asset = GeneratedObjectAsset(
        region_id=region_id,
        candidate_ref=candidate_ref,
        object_ref=object_ref,
        object_mask_ref=object_mask_ref,
        width=max(1, width),
        height=max(1, height),
        raw_alpha_mask_ref=raw_alpha_ref,
        original_object_ref=object_ref,
        original_object_mask_ref=object_mask_ref,
        original_raw_alpha_mask_ref=raw_alpha_ref,
        raw_generated_ref=candidate_ref,
        sam_object_ref=object_ref,
        sam_mask_ref=object_mask_ref,
        mask_source="fixed_replay",
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
        object_model_id=object_model_id,
        object_sampler=object_sampler,
        object_steps=object_steps,
        object_guidance_scale=object_guidance_scale,
        object_seed=object_seed,
    )
    for path in (object_ref, object_mask_ref, raw_alpha_ref):
        if not Path(path).exists():
            raise FileNotFoundError(f"fixed replay asset does not exist: {path}")
    return [region], {region_id: asset}
