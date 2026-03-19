from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image
from scipy.spatial.distance import cosine
from skimage import color
from skimage.feature import hog, local_binary_pattern
from skimage.filters import gabor

from discoverex.application.context import AppContextLike
from discoverex.application.use_cases.gen_verify.background_pipeline import (
    apply_background_canvas_upscale_if_needed,
    apply_background_detail_reconstruction_if_needed,
    build_background_from_inputs,
)
from discoverex.application.use_cases.gen_verify.composite_pipeline import compose_scene
from discoverex.application.use_cases.gen_verify.model_lifecycle import unload_model
from discoverex.application.use_cases.gen_verify.object_pipeline import (
    GeneratedObjectAsset,
    generate_region_objects,
)
from discoverex.application.use_cases.gen_verify.persistence import (
    save_scene,
    track_run,
    write_naturalness_report,
    write_verification_report,
)
from discoverex.application.use_cases.gen_verify.prompt_bundle import (
    build_prompt_tracking_params,
    save_prompt_bundle,
)
from discoverex.application.use_cases.gen_verify.region_prompts import record_layer_candidate
from discoverex.application.use_cases.gen_verify.region_pipeline import generate_regions
from discoverex.application.use_cases.gen_verify.regions.selection import (
    bbox_iou,
    build_candidate_regions,
)
from discoverex.application.use_cases.gen_verify.scene_builder import (
    build_scene,
    generate_run_ids,
)
from discoverex.application.use_cases.gen_verify.types import (
    CompositeResolution,
    PromptBundle,
    PromptStageRecord,
    RegionPromptRecord,
)
from discoverex.application.use_cases.gen_verify.verification_pipeline import (
    run_perception_verification,
    verify_scene,
)
from discoverex.config import PipelineConfig
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background, LayerBBox, LayerItem, LayerType, Scene
from discoverex.models.types import HiddenRegionRequest, PerceptionRequest
from discoverex.runtime_logging import format_seconds, get_logger

logger = get_logger("discoverex.generate.v2")


def run(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    context: AppContextLike,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    started = perf_counter()
    background_asset_ref = str(args.get("background_asset_ref", "") or "")
    background_prompt = str(args.get("background_prompt", "") or "")
    background_negative_prompt = str(args.get("background_negative_prompt", "") or "")
    object_prompt = str(args.get("object_prompt", "") or "")
    object_negative_prompt = str(args.get("object_negative_prompt", "") or "")
    final_prompt = str(args.get("final_prompt", "") or "")
    final_negative_prompt = str(args.get("final_negative_prompt", "") or "")

    run_ids = generate_run_ids()
    scene_dir = (
        Path(context.artifacts_root) / "scenes" / run_ids.scene_id / run_ids.version_id
    )
    background, background_prompt_record = _build_background(
        context=context,
        scene_dir=scene_dir,
        background_asset_ref=background_asset_ref or None,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    )

    if config.region_selection.strategy == "legacy_detr":
        candidate_regions = _detect_regions_legacy(context=context, background=background)
        candidate_regions = candidate_regions[: config.object_variants.default_count]
        generated_objects = _generate_objects(
            context=context,
            scene_dir=scene_dir,
            regions=candidate_regions,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
    else:
        object_count = max(
            1,
            int(args.get("object_count") or config.object_variants.default_count),
        )
        placeholder_regions = _build_placeholder_regions(object_count)
        generated_objects = _generate_objects(
            context=context,
            scene_dir=scene_dir,
            regions=placeholder_regions,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
        candidate_regions = _select_regions_patch_similarity(
            config=config,
            background=background,
            generated_objects=list(generated_objects.values()),
        )
        generated_objects = {
            region.region_id: generated_objects[region.region_id] for region in candidate_regions
        }
        if config.color_harmonization.enabled:
            generated_objects = _harmonize_objects(
                config=config,
                scene_dir=scene_dir,
                background=background,
                regions=candidate_regions,
                generated_objects=generated_objects,
            )

    regions, region_prompt_records = _generate_regions(
        context=context,
        background=background,
        scene_dir=scene_dir,
        regions=candidate_regions,
        generated_objects=generated_objects,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
    )
    scene = build_scene(
        background=background,
        regions=regions,
        model_versions=context.model_versions.model_dump(mode="python"),
        runtime_cfg=context.runtime,
        run_ids=run_ids,
    )

    fx_input_ref = background.asset_ref
    inpaint_ref = background.metadata.get("inpaint_composited_ref")
    if isinstance(inpaint_ref, str) and inpaint_ref:
        fx_input_ref = inpaint_ref

    composite = _compose_scene(
        context=context,
        scene_dir=scene_dir,
        background_asset_ref=fx_input_ref,
        final_prompt=final_prompt,
        final_negative_prompt=final_negative_prompt,
    )
    scene.composite.final_image_ref = composite.image_ref
    _finalize_layers(scene=scene, background=background, fx_input_ref=fx_input_ref)
    _verify_scene(context=context, scene=scene)
    _verify_regions(context=context, scene=scene, scene_dir=scene_dir)
    _persist_outputs(
        context=context,
        scene=scene,
        scene_dir=scene_dir,
        background_prompt_record=background_prompt_record,
        region_prompt_records=region_prompt_records,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
        final_prompt=final_prompt,
        final_negative_prompt=final_negative_prompt,
        fx_input_ref=fx_input_ref,
        composite_artifact=composite.artifact_path,
    )
    logger.info(
        "generate_verify_v2 completed scene_id=%s version_id=%s duration=%s strategy=%s",
        scene.meta.scene_id,
        scene.meta.version_id,
        format_seconds(started),
        config.region_selection.strategy,
    )
    from discoverex.flows.common import build_scene_payload

    return build_scene_payload(
        scene,
        config.runtime.artifacts_root,
        str(execution_snapshot_path) if execution_snapshot_path is not None else None,
        getattr(context, "tracking_run_id", None),
    )


def _build_background(
    *,
    context: AppContextLike,
    scene_dir: Path,
    background_asset_ref: str | None,
    background_prompt: str | None,
    background_negative_prompt: str | None,
) -> tuple[Background, PromptStageRecord]:
    handle = context.background_generator_model.load(
        context.model_versions.background_generator
    )
    try:
        background, prompt_record = build_background_from_inputs(
            context=context,
            scene_dir=scene_dir,
            fx_handle=handle,
            background_asset_ref=background_asset_ref,
            background_prompt=background_prompt,
            background_negative_prompt=background_negative_prompt,
        )
    finally:
        unload_model(context.background_generator_model)
    handle = context.background_upscaler_model.load(context.model_versions.background_upscaler)
    try:
        background = apply_background_canvas_upscale_if_needed(
            background=background,
            context=context,
            scene_dir=scene_dir,
            upscaler_handle=handle,
            prompt=(background_prompt or "").strip(),
            negative_prompt=(background_negative_prompt or "").strip(),
        )
        background = apply_background_detail_reconstruction_if_needed(
            background=background,
            context=context,
            scene_dir=scene_dir,
            upscaler_handle=handle,
            prompt=(background_prompt or "").strip(),
            negative_prompt=(background_negative_prompt or "").strip(),
        )
    finally:
        unload_model(context.background_upscaler_model)
    _materialize_background_asset(background=background, scene_dir=scene_dir)
    return background, prompt_record


def _materialize_background_asset(*, background: Background, scene_dir: Path) -> None:
    source = Path(background.asset_ref)
    if not source.exists() or not source.is_file():
        return
    base_dir = scene_dir / "assets" / "background"
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / source.name
    if source.resolve() == target.resolve():
        return
    target.write_bytes(source.read_bytes())
    background.metadata["source_background_ref"] = background.asset_ref
    background.asset_ref = str(target)


def _detect_regions_legacy(
    *,
    context: AppContextLike,
    background: Background,
) -> list[Region]:
    hidden_handle = context.hidden_region_model.load(
        context.model_versions.hidden_region
    )
    try:
        boxes = context.hidden_region_model.predict(
            hidden_handle,
            HiddenRegionRequest(
                image_ref=background.asset_ref,
                width=background.width,
                height=background.height,
            ),
        )
    finally:
        unload_model(context.hidden_region_model)
    return build_candidate_regions(boxes)


def _build_placeholder_regions(count: int) -> list[Region]:
    regions: list[Region] = []
    for idx in range(count):
        regions.append(
            Region(
                region_id=f"r-{uuid4().hex[:10]}",
                geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=64.0, h=64.0)),
                role=RegionRole.ANSWER if idx == 0 else RegionRole.CANDIDATE,
                source=RegionSource.MANUAL,
                attributes={"proposal_rank": idx + 1},
                version=1,
            )
        )
    return regions


def _generate_objects(
    *,
    context: AppContextLike,
    scene_dir: Path,
    regions: list[Region],
    object_prompt: str,
    object_negative_prompt: str,
) -> dict[str, GeneratedObjectAsset]:
    handle = context.object_generator_model.load(context.model_versions.object_generator)
    try:
        return generate_region_objects(
            context=context,
            scene_dir=scene_dir,
            regions=regions,
            object_handle=handle,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
    finally:
        unload_model(context.object_generator_model)


def _select_regions_patch_similarity(
    *,
    config: PipelineConfig,
    background: Background,
    generated_objects: list[GeneratedObjectAsset],
) -> list[Region]:
    background_image = np.asarray(Image.open(background.asset_ref).convert("RGB"))
    selected_boxes: list[tuple[float, float, float, float]] = []
    regions: list[Region] = []
    for index, asset in enumerate(generated_objects, start=1):
        variants = _build_object_variants(config=config, asset=asset)
        best = _find_best_patch(
            config=config,
            background_image=background_image,
            variants=variants,
            selected_boxes=selected_boxes,
        )
        bbox = best["bbox"]
        selected_boxes.append(bbox)
        region = Region(
            region_id=asset.region_id,
            geometry=Geometry(type="bbox", bbox=BBox(x=bbox[0], y=bbox[1], w=bbox[2], h=bbox[3])),
            role=RegionRole.ANSWER if index == 1 else RegionRole.CANDIDATE,
            source=RegionSource.CANDIDATE_MODEL,
            attributes={
                "proposal_rank": index,
                "selection_strategy": "patch_similarity_v2",
                "selected_variant_id": best["variant_id"],
                "feature_scores": best["feature_scores"],
                "composite_similarity_score": best["score"],
            },
            version=1,
        )
        regions.append(region)
    return regions


def _build_object_variants(
    *,
    config: PipelineConfig,
    asset: GeneratedObjectAsset,
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    with Image.open(asset.object_ref).convert("RGBA") as object_image:
        for rotation in config.object_variants.rotation_degrees:
            rotated = object_image.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
            for scale in config.object_variants.scale_factors:
                width = max(1, int(round(rotated.width * scale)))
                height = max(1, int(round(rotated.height * scale)))
                scaled = rotated.resize((width, height), Image.Resampling.LANCZOS)
                variants.append(
                    {
                        "variant_id": f"rot{rotation:g}-scale{scale:.2f}",
                        "image": _pad_rgba(scaled, config.object_variants.canvas_padding),
                    }
                )
                if len(variants) >= config.object_variants.max_variants_per_object:
                    return variants
    return variants


def _pad_rgba(image: Image.Image, padding: int) -> Image.Image:
    canvas = Image.new(
        "RGBA",
        (image.width + padding * 2, image.height + padding * 2),
        (0, 0, 0, 0),
    )
    canvas.paste(image, (padding, padding), image)
    return canvas


def _find_best_patch(
    *,
    config: PipelineConfig,
    background_image: np.ndarray,
    variants: list[dict[str, Any]],
    selected_boxes: list[tuple[float, float, float, float]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    height, width = background_image.shape[:2]
    candidate_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
    variant_feature_cache: dict[tuple[str, int, int], dict[str, np.ndarray]] = {}
    for variant in variants:
        rgba = variant["image"]
        variant_id = str(variant["variant_id"])
        patch_w = min(width, max(1, max(config.patch_similarity.min_patch_side, rgba.width)))
        patch_h = min(height, max(1, max(config.patch_similarity.min_patch_side, rgba.height)))
        for scale_factor in config.region_selection.scale_factors:
            scaled_w = min(width, max(1, int(round(patch_w * scale_factor))))
            scaled_h = min(height, max(1, int(round(patch_h * scale_factor))))
            cache_key = (scaled_w, scaled_h)
            candidates = candidate_cache.get(cache_key)
            if candidates is None:
                candidates = _build_patch_candidates(
                    config=config,
                    background_image=background_image,
                    patch_size=cache_key,
                )
                candidate_cache[cache_key] = candidates
            variant_cache_key = (variant_id, scaled_w, scaled_h)
            variant_features = variant_feature_cache.get(variant_cache_key)
            if variant_features is None:
                variant_features = _extract_feature_bundle(
                    np.asarray(
                        rgba.resize(
                            (scaled_w, scaled_h), Image.Resampling.LANCZOS
                        ).convert("RGB")
                    ),
                    config=config,
                )
                variant_feature_cache[variant_cache_key] = variant_features
            for candidate in candidates:
                bbox = candidate["bbox"]
                if any(
                    bbox_iou(bbox, taken) > config.region_selection.iou_threshold
                    for taken in selected_boxes
                ):
                    continue
                feature_scores = _score_feature_bundle(
                    config=config,
                    variant_features=variant_features,
                    patch_features=candidate["features"],
                )
                score = sum(feature_scores.values())
                if best is None or score > float(best["score"]):
                    best = {
                        "bbox": bbox,
                        "score": score,
                        "variant_id": variant_id,
                        "feature_scores": feature_scores,
                    }
    if best is None:
        raise RuntimeError("patch_similarity_v2 could not find a valid candidate patch")
    return best


def _build_patch_candidates(
    *,
    config: PipelineConfig,
    background_image: np.ndarray,
    patch_size: tuple[int, int],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    height, width = background_image.shape[:2]
    patch_w, patch_h = patch_size
    stride_x = max(8, int(round(patch_w * config.region_selection.stride_ratio)))
    stride_y = max(8, int(round(patch_h * config.region_selection.stride_ratio)))
    for top in range(0, max(1, height - patch_h + 1), stride_y):
        for left in range(0, max(1, width - patch_w + 1), stride_x):
            patch = background_image[top : top + patch_h, left : left + patch_w]
            if patch.size == 0:
                continue
            candidates.append(
                {
                    "bbox": (float(left), float(top), float(patch_w), float(patch_h)),
                    "features": _extract_feature_bundle(patch, config=config),
                }
            )
    return candidates


def _extract_feature_bundle(
    image: np.ndarray,
    *,
    config: PipelineConfig,
) -> dict[str, np.ndarray]:
    return {
        "lab": _normalize_feature_vector(_lab_features(image)),
        "lbp": _normalize_feature_vector(_lbp_features(image, config=config)),
        "gabor": _normalize_feature_vector(_gabor_features(image, config=config)),
        "hog": _normalize_feature_vector(_hog_features(image, config=config)),
    }


def _score_feature_bundle(
    *,
    config: PipelineConfig,
    variant_features: dict[str, np.ndarray],
    patch_features: dict[str, np.ndarray],
) -> dict[str, float]:
    weights = {
        "lab": config.patch_similarity.lab_weight,
        "lbp": config.patch_similarity.lbp_weight,
        "gabor": config.patch_similarity.gabor_weight,
        "hog": config.patch_similarity.hog_weight,
    }
    weight_total = max(1e-8, float(sum(weights.values())))
    scores = {
        "lab": _normalized_similarity(
            _cosine_similarity(variant_features["lab"], patch_features["lab"])
        ),
        "lbp": _cosine_similarity(
            variant_features["lbp"],
            patch_features["lbp"],
        ),
        "gabor": _cosine_similarity(
            variant_features["gabor"],
            patch_features["gabor"],
        ),
        "hog": _cosine_similarity(
            variant_features["hog"],
            patch_features["hog"],
        ),
    }
    return {
        name: (_normalized_similarity(score) * weights[name]) / weight_total
        for name, score in scores.items()
    }


def _lab_features(image: np.ndarray) -> np.ndarray:
    lab = color.rgb2lab(np.clip(image.astype(np.float32) / 255.0, 0.0, 1.0))
    mean = lab.reshape(-1, 3).mean(axis=0)
    std = lab.reshape(-1, 3).std(axis=0)
    return np.concatenate([mean, std])


def _lbp_features(image: np.ndarray, *, config: PipelineConfig) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    lbp = local_binary_pattern(
        gray,
        P=config.patch_similarity.lbp_points,
        R=config.patch_similarity.lbp_radius,
        method="uniform",
    )
    hist, _ = np.histogram(
        lbp.ravel(),
        bins=config.patch_similarity.lbp_points + 2,
        range=(0, config.patch_similarity.lbp_points + 2),
        density=True,
    )
    return hist.astype(np.float32)


def _gabor_features(image: np.ndarray, *, config: PipelineConfig) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    feats: list[float] = []
    for frequency in config.patch_similarity.gabor_frequencies:
        for theta in config.patch_similarity.gabor_thetas:
            real, imag = gabor(gray, frequency=frequency, theta=theta)
            feats.extend(
                [
                    float(real.mean()),
                    float(real.std()),
                    float(imag.mean()),
                    float(imag.std()),
                ]
            )
    return np.asarray(feats, dtype=np.float32)


def _hog_features(image: np.ndarray, *, config: PipelineConfig) -> np.ndarray:
    min_side = max(8, config.patch_similarity.hog_pixels_per_cell)
    if image.shape[0] < min_side or image.shape[1] < min_side:
        image = np.asarray(
            Image.fromarray(image).resize(
                (max(min_side, image.shape[1]), max(min_side, image.shape[0])),
                Image.Resampling.BILINEAR,
            )
        )
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    vector = hog(
        gray,
        orientations=config.patch_similarity.hog_orientations,
        pixels_per_cell=(
            config.patch_similarity.hog_pixels_per_cell,
            config.patch_similarity.hog_pixels_per_cell,
        ),
        cells_per_block=(1, 1),
        feature_vector=True,
    )
    return np.asarray(vector, dtype=np.float32)


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    if np.allclose(left, 0.0) or np.allclose(right, 0.0):
        return 0.0
    return max(0.0, 1.0 - float(cosine(left, right)))


def _normalize_feature_vector(vector: np.ndarray) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32).reshape(-1)
    if array.size == 0:
        return array
    finite = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
    norm = float(np.linalg.norm(finite))
    if norm <= 1e-8:
        return finite
    return finite / norm


def _normalized_similarity(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(np.clip(value, 0.0, 1.0))


def _harmonize_objects(
    *,
    config: PipelineConfig,
    scene_dir: Path,
    background: Background,
    regions: list[Region],
    generated_objects: dict[str, GeneratedObjectAsset],
) -> dict[str, GeneratedObjectAsset]:
    background_image = np.asarray(Image.open(background.asset_ref).convert("RGB"))
    output: dict[str, GeneratedObjectAsset] = {}
    for region in regions:
        asset = generated_objects[region.region_id]
        bbox = region.geometry.bbox
        left = max(0, int(round(bbox.x)))
        top = max(0, int(round(bbox.y)))
        right = min(background_image.shape[1], int(round(bbox.x + bbox.w)))
        bottom = min(background_image.shape[0], int(round(bbox.y + bbox.h)))
        patch = background_image[top:bottom, left:right]
        if patch.size == 0:
            output[region.region_id] = asset
            continue
        object_image = Image.open(asset.object_ref).convert("RGBA")
        harmonized = _harmonize_rgba(
            rgba=object_image,
            patch=patch,
            alpha=config.color_harmonization.blend_alpha,
        )
        output_path = scene_dir / "assets" / "objects" / f"{region.region_id}.harmonized.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        harmonized.save(output_path)
        output[region.region_id] = replace(asset, object_ref=str(output_path))
    return output


def _harmonize_rgba(*, rgba: Image.Image, patch: np.ndarray, alpha: float) -> Image.Image:
    rgba_array = np.asarray(rgba).astype(np.float32)
    rgb = rgba_array[..., :3]
    alpha_channel = rgba_array[..., 3:4] / 255.0
    if np.count_nonzero(alpha_channel) == 0:
        return rgba
    obj_lab = color.rgb2lab(np.clip(rgb / 255.0, 0.0, 1.0))
    patch_lab = color.rgb2lab(np.clip(patch.astype(np.float32) / 255.0, 0.0, 1.0))
    patch_mean = patch_lab.reshape(-1, 3).mean(axis=0)
    obj_mean = obj_lab.reshape(-1, 3).mean(axis=0)
    adjusted_lab = obj_lab + (patch_mean - obj_mean) * float(alpha)
    adjusted_rgb = np.clip(color.lab2rgb(adjusted_lab) * 255.0, 0.0, 255.0)
    merged = np.concatenate([adjusted_rgb, alpha_channel * 255.0], axis=2)
    return Image.fromarray(merged.astype(np.uint8), mode="RGBA")


def _generate_regions(
    *,
    context: AppContextLike,
    background: Background,
    scene_dir: Path,
    regions: list[Region],
    generated_objects: dict[str, GeneratedObjectAsset],
    object_prompt: str,
    object_negative_prompt: str,
) -> tuple[list[Region], list[RegionPromptRecord]]:
    handle = context.inpaint_model.load(context.model_versions.inpaint)
    try:
        return generate_regions(
            context=context,
            background=background,
            scene_dir=scene_dir,
            regions=regions,
            generated_objects=generated_objects,
            inpaint_handle=handle,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
    finally:
        unload_model(context.inpaint_model)


def _compose_scene(
    *,
    context: AppContextLike,
    scene_dir: Path,
    background_asset_ref: str,
    final_prompt: str,
    final_negative_prompt: str,
) -> CompositeResolution:
    fx_handle = context.fx_model.load(context.model_versions.fx)
    try:
        return compose_scene(
            context=context,
            background_asset_ref=background_asset_ref,
            scene_dir=scene_dir,
            fx_handle=fx_handle,
            prompt=final_prompt or "polished hidden object puzzle final render",
            negative_prompt=final_negative_prompt or "blurry, low quality, artifact",
        )
    finally:
        unload_model(context.fx_model)


def _verify_scene(*, context: AppContextLike, scene: Scene) -> None:
    handle = context.perception_model.load(context.model_versions.perception)
    try:
        verify_scene(scene=scene, context=context, perception_handle=handle)
    finally:
        unload_model(context.perception_model)


def _verify_regions(*, context: AppContextLike, scene: Scene, scene_dir: Path) -> None:
    handle = context.perception_model.load(context.model_versions.perception)
    try:
        image = Image.open(scene.composite.final_image_ref).convert("RGB")
        for region in scene.regions:
            bbox = region.geometry.bbox
            crop = image.crop(
                (
                    int(round(bbox.x)),
                    int(round(bbox.y)),
                    int(round(bbox.x + bbox.w)),
                    int(round(bbox.y + bbox.h)),
                )
            )
            crop_path = scene_dir / "assets" / "verification" / f"{region.region_id}.png"
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_path)
            pred = context.perception_model.predict(
                handle,
                PerceptionRequest(
                    image_ref=str(crop_path),
                    region_count=1,
                    regions=[{"region_id": region.region_id, "role": region.role.value}],
                    question_context=scene.goal.goal_type.value,
                ),
            )
            result = run_perception_verification(
                scene=scene,
                confidence=float(pred["confidence"]),
                pass_threshold=float(context.thresholds.perception_pass),
            )
            region.attributes["verify_score"] = result.score
            region.attributes["verify_pass"] = result.pass_
    finally:
        unload_model(context.perception_model)


def _persist_outputs(
    *,
    context: AppContextLike,
    scene: Scene,
    scene_dir: Path,
    background_prompt_record: PromptStageRecord,
    region_prompt_records: list[RegionPromptRecord],
    object_prompt: str,
    object_negative_prompt: str,
    final_prompt: str,
    final_negative_prompt: str,
    fx_input_ref: str,
    composite_artifact: Path | None,
) -> None:
    prompt_bundle = PromptBundle(
        input_mode=background_prompt_record.mode,
        background=background_prompt_record.model_copy(
            update={"output_ref": background_prompt_record.output_ref or scene.background.asset_ref}
        ),
        object=PromptStageRecord(
            mode="shared",
            prompt=object_prompt,
            negative_prompt=object_negative_prompt,
        ),
        final_fx=PromptStageRecord(
            mode="default",
            prompt=final_prompt or "polished hidden object puzzle final render",
            negative_prompt=final_negative_prompt or "blurry, low quality, artifact",
            source_ref=fx_input_ref,
            output_ref=scene.composite.final_image_ref,
        ),
        regions=region_prompt_records,
    )
    prompt_bundle_path = save_prompt_bundle(scene_dir, prompt_bundle)
    saved_dir = save_scene(context=context, scene=scene)
    write_verification_report(context=context, saved_dir=saved_dir, scene=scene)
    naturalness_report = write_naturalness_report(saved_dir=saved_dir, scene=scene)
    track_run(
        context=context,
        scene=scene,
        saved_dir=saved_dir,
        composite_artifact=composite_artifact,
        prompt_bundle_artifact=prompt_bundle_path,
        naturalness_artifact=naturalness_report,
        extra_params=build_prompt_tracking_params(prompt_bundle),
    )


def _finalize_layers(scene: Scene, background: Background, fx_input_ref: str) -> None:
    layers = list(scene.layers.items)
    next_order = max((layer.order for layer in layers), default=0) + 1
    candidates = background.metadata.get("inpaint_layer_candidates", [])
    if isinstance(candidates, list):
        for idx, item in enumerate(candidates):
            if not isinstance(item, dict):
                continue
            patch_ref = (
                item.get("layer_image_ref")
                or item.get("object_image_ref")
                or item.get("patch_image_ref")
            )
            bbox = item.get("bbox")
            region_id = item.get("region_id")
            if not isinstance(patch_ref, str) or not isinstance(bbox, dict):
                continue
            try:
                layer_bbox = LayerBBox(
                    x=float(bbox["x"]),
                    y=float(bbox["y"]),
                    w=float(bbox["w"]),
                    h=float(bbox["h"]),
                )
            except Exception:
                continue
            layers.append(
                LayerItem(
                    layer_id=f"layer-inpaint-{idx}",
                    type=LayerType.INPAINT_PATCH,
                    image_ref=patch_ref,
                    bbox=layer_bbox,
                    z_index=10 + idx,
                    order=next_order,
                    source_region_id=str(region_id) if region_id is not None else None,
                )
            )
            next_order += 1
    if fx_input_ref != background.asset_ref:
        layers.append(
            LayerItem(
                layer_id="layer-composite-pre-fx",
                type=LayerType.COMPOSITE,
                image_ref=fx_input_ref,
                z_index=900,
                order=next_order,
            )
        )
        next_order += 1
    layers.append(
        LayerItem(
            layer_id="layer-fx-final",
            type=LayerType.FX_OVERLAY,
            image_ref=scene.composite.final_image_ref,
            z_index=1000,
            order=next_order,
        )
    )
    scene.layers.items = layers
