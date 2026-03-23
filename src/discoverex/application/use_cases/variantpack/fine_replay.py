from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from discoverex.application.use_cases.generate_verify_v2 import (
    _extract_feature_bundle,
    _iter_local_refined_bboxes,
    _score_feature_bundle,
)
from discoverex.config import PipelineConfig
from discoverex.domain.region import BBox, Region
from discoverex.domain.scene import Background


def refine_replay_regions(
    *,
    config: PipelineConfig,
    scene_dir: Path,
    background: Background,
    regions: list[Region],
) -> list[Region]:
    background_image = np.asarray(Image.open(background.asset_ref).convert("RGB"))
    selected_boxes: list[tuple[float, float, float, float]] = []
    feature_names = tuple(
        name
        for name, weight in (
            ("lab", config.patch_similarity.lab_weight),
            ("lbp", config.patch_similarity.lbp_weight),
            ("gabor", config.patch_similarity.gabor_weight),
            ("hog", config.patch_similarity.hog_weight),
        )
        if weight > 0.0
    )
    output: list[Region] = []
    for region in regions:
        coarse_ref = str(region.attributes.get("coarse_variant_image_ref", "") or "")
        coarse_config_ref = str(
            region.attributes.get("coarse_variant_config_ref", "") or ""
        )
        if not coarse_ref:
            raise ValueError(f"replay region {region.region_id} missing coarse variant image")
        variant = Image.open(coarse_ref).convert("RGBA")
        try:
            variant_rgb = np.asarray(variant.convert("RGB"))
        finally:
            variant.close()
        variant_features = _extract_feature_bundle(
            variant_rgb,
            config=config,
            feature_names=feature_names,
        )
        coarse_bbox = (
            float(region.geometry.bbox.x),
            float(region.geometry.bbox.y),
            float(region.geometry.bbox.w),
            float(region.geometry.bbox.h),
        )
        best_bbox = coarse_bbox
        best_scores: dict[str, float] = {}
        best_total = -1.0
        for bbox in _iter_local_refined_bboxes(
            coarse_bbox,
            image_size=(background_image.shape[1], background_image.shape[0]),
            iou_threshold=config.region_selection.iou_threshold,
            selected_boxes=selected_boxes,
        ):
            left = int(bbox[0])
            top = int(bbox[1])
            patch_w = int(bbox[2])
            patch_h = int(bbox[3])
            patch = background_image[top : top + patch_h, left : left + patch_w]
            patch_features = _extract_feature_bundle(
                patch,
                config=config,
                feature_names=feature_names,
            )
            scores = _score_feature_bundle(
                config=config,
                variant_features=variant_features,
                patch_features=patch_features,
                feature_names=feature_names,
            )
            total = float(sum(scores.values()))
            if total > best_total:
                best_total = total
                best_bbox = bbox
                best_scores = scores
        selected_boxes.append(best_bbox)
        updated = region.model_copy(deep=True)
        updated.geometry.bbox = BBox(
            x=float(best_bbox[0]),
            y=float(best_bbox[1]),
            w=float(best_bbox[2]),
            h=float(best_bbox[3]),
        )
        updated.attributes["selection_strategy"] = "replay_fixture_fine"
        updated.attributes["feature_scores"] = best_scores
        updated.attributes["composite_similarity_score"] = best_total
        updated.attributes.update(
            _write_fine_selection_artifacts(
                scene_dir=scene_dir,
                region_id=region.region_id,
                bbox=best_bbox,
                score=best_total,
                feature_scores=best_scores,
                variant_image_ref=coarse_ref,
                variant_config_ref=coarse_config_ref,
                selected_variant_id=str(
                    region.attributes.get("selected_variant_id", "") or "fixture-selected"
                ),
                selected_variant_config=dict(
                    region.attributes.get("selected_variant_config", {}) or {}
                ),
            )
        )
        output.append(updated)
    return output


def _write_fine_selection_artifacts(
    *,
    scene_dir: Path,
    region_id: str,
    bbox: tuple[float, float, float, float],
    score: float,
    feature_scores: dict[str, float],
    variant_image_ref: str,
    variant_config_ref: str,
    selected_variant_id: str,
    selected_variant_config: dict[str, Any],
) -> dict[str, str]:
    artifact_dir = scene_dir / "assets" / "patch_selection" / region_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    image_path = artifact_dir / "fine.selected.variant.png"
    config_path = artifact_dir / "fine.selected.variant.json"
    selection_path = artifact_dir / "fine.selection.json"
    with Image.open(variant_image_ref).convert("RGBA") as image:
        image.save(image_path)
    if variant_config_ref and Path(variant_config_ref).exists():
        config_payload = json.loads(Path(variant_config_ref).read_text(encoding="utf-8"))
    else:
        config_payload = {}
    if not isinstance(config_payload, dict):
        config_payload = {}
    config_payload.update(
        {
            "region_id": region_id,
            "stage": "fine",
            "variant_id": selected_variant_id,
            "variant_config": selected_variant_config,
            "variant_image_ref": str(image_path),
        }
    )
    config_path.write_text(
        json.dumps(config_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    selection_payload = {
        "region_id": region_id,
        "stage": "fine",
        "selection_strategy": "replay_fixture_fine",
        "selected_variant_id": selected_variant_id,
        "selected_bbox": {
            "x": float(bbox[0]),
            "y": float(bbox[1]),
            "w": float(bbox[2]),
            "h": float(bbox[3]),
        },
        "score": float(score),
        "feature_scores": dict(feature_scores),
        "variant_image_ref": str(image_path),
        "variant_config_ref": str(config_path),
    }
    selection_path.write_text(
        json.dumps(selection_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"patch_selection_fine_ref": str(selection_path)}
