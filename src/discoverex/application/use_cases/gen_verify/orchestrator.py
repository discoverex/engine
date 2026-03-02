from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from discoverex.bootstrap import AppContext
from discoverex.domain.scene import Scene

from .composite_pipeline import compose_scene
from .persistence import save_scene, track_run, write_verification_report
from .region_pipeline import generate_regions
from .scene_builder import build_background, build_scene, generate_run_ids
from .verification_pipeline import verify_scene


def run(background_asset_ref: str, context: AppContext) -> Scene:
    runtime_cfg = context.runtime
    model_versions = context.model_versions
    run_ids = generate_run_ids()

    hidden_handle = context.hidden_region_model.load(model_versions.hidden_region)
    inpaint_handle = context.inpaint_model.load(model_versions.inpaint)
    perception_handle = context.perception_model.load(model_versions.perception)
    fx_handle = context.fx_model.load(model_versions.fx)

    background = build_background(background_asset_ref, runtime_cfg)
    regions = generate_regions(
        context=context,
        background=background,
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

    scene_dir = Path(context.artifacts_root) / "scenes" / run_ids.scene_id / run_ids.version_id
    composite = compose_scene(
        context=context,
        background_asset_ref=background.asset_ref,
        scene_dir=scene_dir,
        fx_handle=fx_handle,
    )
    scene.composite.final_image_ref = composite.image_ref

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
