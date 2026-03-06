from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from discoverex.application.context import AppContextLike
from discoverex.domain.scene import LayerBBox, LayerItem, LayerType, Scene

from .composite_pipeline import compose_scene
from .persistence import save_scene, track_run, write_verification_report
from .region_pipeline import generate_regions
from .scene_builder import build_background, build_scene, generate_run_ids
from .verification_pipeline import verify_scene


def run(background_asset_ref: str, context: AppContextLike) -> Scene:
    runtime_cfg = context.runtime
    model_versions = context.model_versions
    run_ids = generate_run_ids()

    hidden_handle = context.hidden_region_model.load(model_versions.hidden_region)
    inpaint_handle = context.inpaint_model.load(model_versions.inpaint)
    perception_handle = context.perception_model.load(model_versions.perception)
    fx_handle = context.fx_model.load(model_versions.fx)
    scene_dir = (
        Path(context.artifacts_root) / "scenes" / run_ids.scene_id / run_ids.version_id
    )

    background = build_background(background_asset_ref, runtime_cfg)
    _materialize_background_asset(background=background, scene_dir=scene_dir)
    regions = generate_regions(
        context=context,
        background=background,
        scene_dir=scene_dir,
        hidden_handle=hidden_handle,
        inpaint_handle=inpaint_handle,
    )
    scene = build_scene(
        background=background,
        regions=regions,
        model_versions=model_versions.model_dump(mode="python"),
        runtime_cfg=runtime_cfg,
        run_ids=run_ids,
    )

    fx_input_ref = background.asset_ref
    inpaint_ref = background.metadata.get("inpaint_composited_ref")
    if isinstance(inpaint_ref, str) and inpaint_ref:
        fx_input_ref = inpaint_ref
    composite = compose_scene(
        context=context,
        background_asset_ref=fx_input_ref,
        scene_dir=scene_dir,
        fx_handle=fx_handle,
    )
    scene.composite.final_image_ref = composite.image_ref
    _finalize_layers(scene=scene, background=background, fx_input_ref=fx_input_ref)

    verify_scene(scene=scene, context=context, perception_handle=perception_handle)
    scene.meta.updated_at = datetime.now(timezone.utc)

    saved_dir = save_scene(context=context, scene=scene)
    write_verification_report(context=context, saved_dir=saved_dir, scene=scene)
    track_run(
        context=context,
        scene=scene,
        saved_dir=saved_dir,
        composite_artifact=composite.artifact_path,
    )
    return scene


def _materialize_background_asset(background, scene_dir: Path) -> None:  # type: ignore[no-untyped-def]
    source = Path(background.asset_ref)
    if not source.exists() or not source.is_file():
        return
    base_dir = scene_dir / "layers" / "base"
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / source.name
    shutil.copy2(source, target)
    background.metadata["source_background_ref"] = background.asset_ref
    background.asset_ref = str(target)


def _finalize_layers(scene: Scene, background, fx_input_ref: str) -> None:  # type: ignore[no-untyped-def]
    layers = list(scene.layers.items)
    next_order = max((layer.order for layer in layers), default=0) + 1

    candidates = background.metadata.get("inpaint_layer_candidates", [])
    if isinstance(candidates, list):
        for idx, item in enumerate(candidates):
            if not isinstance(item, dict):
                continue
            patch_ref = item.get("patch_image_ref")
            bbox = item.get("bbox")
            region_id = item.get("region_id")
            if not isinstance(patch_ref, str):
                continue
            if not isinstance(bbox, dict):
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
