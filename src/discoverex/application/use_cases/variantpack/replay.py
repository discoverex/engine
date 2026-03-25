from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource


def has_fixed_replay_inputs(args: dict[str, Any]) -> bool:
    return bool(
        str(args.get("object_image_ref", "") or "").strip()
        and str(args.get("object_mask_ref", "") or "").strip()
        and isinstance(args.get("bbox"), dict)
    )


def has_replay_fixture_inputs(args: dict[str, Any]) -> bool:
    return bool(str(args.get("replay_fixture_ref", "") or "").strip())


def replay_background_asset_ref(args: dict[str, Any]) -> str | None:
    if not has_replay_fixture_inputs(args):
        return None
    fixture = load_replay_fixture(args)
    value = str(fixture.get("background_asset_ref", "") or "").strip()
    return value or None


def load_replay_fixture(args: dict[str, Any]) -> dict[str, Any]:
    fixture_ref = str(args.get("replay_fixture_ref", "") or "").strip()
    if not fixture_ref:
        raise ValueError("replay fixture requires args.replay_fixture_ref")
    fixture_path = Path(fixture_ref)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("replay fixture must decode to an object")
    regions = payload.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("replay fixture requires a non-empty regions array")
    normalized = dict(payload)
    normalized["background_asset_ref"] = _resolve_fixture_path(
        base=fixture_path,
        value=payload.get("background_asset_ref"),
    )
    normalized["regions"] = [
        _normalize_replay_region(base=fixture_path, item=item, index=index)
        for index, item in enumerate(regions, start=1)
    ]
    normalized["fixture_path"] = str(fixture_path.resolve())
    return normalized


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


def build_replay_fixture_inputs(
    *,
    args: dict[str, Any],
    scene_dir: Path,
    object_prompt: str,
    object_negative_prompt: str,
    object_model_id: str = "",
    object_sampler: str = "",
    object_steps: int = 0,
    object_guidance_scale: float = 0.0,
    object_seed: int | None = None,
) -> tuple[list[Region], dict[str, GeneratedObjectAsset], dict[str, Any]]:
    fixture = load_replay_fixture(args)
    regions: list[Region] = []
    generated: dict[str, GeneratedObjectAsset] = {}
    for item in fixture["regions"]:
        region_id = str(item["region_id"])
        coarse_bbox = item["coarse_selected_bbox"]
        region = Region(
            region_id=region_id,
            geometry=Geometry(
                type="bbox",
                bbox=BBox(
                    x=float(coarse_bbox["x"]),
                    y=float(coarse_bbox["y"]),
                    w=float(coarse_bbox["w"]),
                    h=float(coarse_bbox["h"]),
                ),
            ),
            role=RegionRole.ANSWER,
            source=RegionSource.MANUAL,
            attributes={
                "proposal_rank": int(item["proposal_rank"]),
                "selection_strategy": "replay_fixture_coarse",
                "fixture_region_id": region_id,
                "selected_variant_id": str(item["selected_variant_id"]),
                "selected_variant_config": dict(item["selected_variant_config"]),
                "object_label": str(item.get("object_label", "") or region_id),
                "object_prompt": str(item.get("object_prompt", "") or object_prompt),
                "object_negative_prompt": str(
                    item.get("object_negative_prompt", "") or object_negative_prompt
                ),
                "patch_selection_coarse_ref": str(item["coarse_selection_ref"]),
                "coarse_variant_image_ref": str(item["coarse_variant_image_ref"]),
                "coarse_variant_config_ref": str(item["coarse_variant_config_ref"]),
            },
            version=1,
        )
        regions.append(region)
        generated[region_id] = _materialize_replay_asset(
            scene_dir=scene_dir,
            region_id=region_id,
            variant_image_ref=str(item["coarse_variant_image_ref"]),
            object_prompt=str(item.get("object_prompt", "") or object_prompt),
            object_negative_prompt=str(
                item.get("object_negative_prompt", "") or object_negative_prompt
            ),
            object_model_id=object_model_id,
            object_sampler=object_sampler,
            object_steps=object_steps,
            object_guidance_scale=object_guidance_scale,
            object_seed=object_seed,
        )
    return regions, generated, fixture


def _normalize_replay_region(
    *,
    base: Path,
    item: Any,
    index: int,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("each replay fixture region must be an object")
    region_id = str(item.get("region_id", "")).strip() or f"replay-region-{index:03d}"
    coarse_bbox = item.get("coarse_selected_bbox")
    if not isinstance(coarse_bbox, dict):
        raise ValueError(f"replay fixture region {region_id} requires coarse_selected_bbox")
    selected_variant_config = item.get("selected_variant_config", {})
    if not isinstance(selected_variant_config, dict):
        selected_variant_config = {}
    normalized = {
        "region_id": region_id,
        "proposal_rank": int(item.get("proposal_rank", index)),
        "object_label": str(item.get("object_label", "")).strip() or region_id,
        "object_prompt": str(item.get("object_prompt", "")).strip(),
        "object_negative_prompt": str(item.get("object_negative_prompt", "")).strip(),
        "selected_variant_id": str(item.get("selected_variant_id", "")).strip()
        or "fixture-selected",
        "selected_variant_config": selected_variant_config,
        "coarse_selection_ref": _require_fixture_path(
            base=base,
            value=item.get("coarse_selection_ref"),
            label=f"{region_id}.coarse_selection_ref",
        ),
        "coarse_variant_image_ref": _require_fixture_path(
            base=base,
            value=item.get("coarse_variant_image_ref"),
            label=f"{region_id}.coarse_variant_image_ref",
        ),
        "coarse_variant_config_ref": _require_fixture_path(
            base=base,
            value=item.get("coarse_variant_config_ref"),
            label=f"{region_id}.coarse_variant_config_ref",
        ),
        "coarse_selected_bbox": {
            "x": float(coarse_bbox["x"]),
            "y": float(coarse_bbox["y"]),
            "w": float(coarse_bbox["w"]),
            "h": float(coarse_bbox["h"]),
        },
    }
    return normalized


def _materialize_replay_asset(
    *,
    scene_dir: Path,
    region_id: str,
    variant_image_ref: str,
    object_prompt: str,
    object_negative_prompt: str,
    object_model_id: str,
    object_sampler: str,
    object_steps: int,
    object_guidance_scale: float,
    object_seed: int | None,
) -> GeneratedObjectAsset:
    source = Path(variant_image_ref)
    if not source.exists():
        raise FileNotFoundError(f"replay fixture variant does not exist: {source}")
    object_out = scene_dir / "assets" / "objects" / f"{region_id}.selected.png"
    mask_out = scene_dir / "assets" / "masks" / f"{region_id}.selected.mask.png"
    raw_alpha_out = (
        scene_dir / "assets" / "masks" / f"{region_id}.selected.raw-alpha-mask.png"
    )
    object_out.parent.mkdir(parents=True, exist_ok=True)
    mask_out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source).convert("RGBA") as image:
        mask = image.getchannel("A")
        image.save(object_out)
        mask.save(mask_out)
        mask.save(raw_alpha_out)
        tight_bbox = mask.getbbox()
        width = max(1, tight_bbox[2] - tight_bbox[0]) if tight_bbox else image.width
        height = max(1, tight_bbox[3] - tight_bbox[1]) if tight_bbox else image.height
    return GeneratedObjectAsset(
        region_id=region_id,
        candidate_ref=str(object_out),
        object_ref=str(object_out),
        object_mask_ref=str(mask_out),
        raw_alpha_mask_ref=str(raw_alpha_out),
        original_object_ref=str(object_out),
        original_object_mask_ref=str(mask_out),
        original_raw_alpha_mask_ref=str(raw_alpha_out),
        raw_generated_ref=str(object_out),
        sam_object_ref=str(object_out),
        sam_mask_ref=str(mask_out),
        mask_source="replay_fixture",
        width=width,
        height=height,
        tight_bbox=tight_bbox,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
        object_model_id=object_model_id,
        object_sampler=object_sampler,
        object_steps=object_steps,
        object_guidance_scale=object_guidance_scale,
        object_seed=object_seed,
    )


def _resolve_fixture_path(*, base: Path, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        path = (base.parent / path).resolve()
    return str(path)


def _require_fixture_path(*, base: Path, value: Any, label: str) -> str:
    resolved = _resolve_fixture_path(base=base, value=value)
    if not resolved:
        raise ValueError(f"replay fixture requires {label}")
    if not Path(resolved).exists():
        raise FileNotFoundError(f"replay fixture path does not exist: {resolved}")
    return resolved
