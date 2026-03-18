from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from prefect import flow, task

from discoverex.application.context import AppContextLike
from discoverex.application.use_cases.gen_verify.background_pipeline import (
    apply_background_canvas_upscale_if_needed,
    apply_background_detail_reconstruction_if_needed,
    build_background_from_inputs,
)
from discoverex.application.use_cases.gen_verify.composite_pipeline import compose_scene
from discoverex.application.use_cases.gen_verify.model_lifecycle import unload_model
from discoverex.application.use_cases.gen_verify.object_pipeline import (
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
from discoverex.application.use_cases.gen_verify.region_pipeline import (
    build_candidate_regions,
    generate_regions,
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
    RunIds,
)
from discoverex.application.use_cases.gen_verify.verification_pipeline import (
    verify_scene,
)
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig
from discoverex.domain.scene import Background, LayerBBox, LayerItem, LayerType, Scene
from discoverex.models.types import HiddenRegionRequest
from discoverex.runtime_logging import format_seconds, get_logger

from .common import build_scene_payload

logger = get_logger("discoverex.generate.flow")


@task(name="discoverex-generate-context", persist_result=False)
def _build_context(
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> AppContextLike:
    return build_context(
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


@task(name="discoverex-generate-run-ids", persist_result=False)
def _generate_run_ids() -> RunIds:
    return generate_run_ids()


@task(name="discoverex-generate-materialize-bg", persist_result=False)
def _materialize_background_asset(
    background: Background, scene_dir: Path
) -> Background:
    source = Path(background.asset_ref)
    if source.exists() and source.is_file():
        base_dir = scene_dir / "layers" / "base"
        base_dir.mkdir(parents=True, exist_ok=True)
        target = base_dir / source.name
        if source.resolve() == target.resolve():
            return background
        shutil.copy2(source, target)
        background.metadata["source_background_ref"] = background.asset_ref
        background.asset_ref = str(target)
    return background


@task(name="discoverex-generate-background", persist_result=False)
def _build_background_stage(
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
        return build_background_from_inputs(
            context=context,
            scene_dir=scene_dir,
            fx_handle=handle,
            background_asset_ref=background_asset_ref,
            background_prompt=background_prompt,
            background_negative_prompt=background_negative_prompt,
        )
    finally:
        unload_model(context.background_generator_model)


@task(name="discoverex-generate-background-canvas-upscale", persist_result=False)
def _background_canvas_upscale_stage(
    *,
    context: AppContextLike,
    scene_dir: Path,
    background: Background,
    background_prompt: str | None,
    background_negative_prompt: str | None,
) -> Background:
    handle = context.background_generator_model.load(
        context.model_versions.background_generator
    )
    try:
        return apply_background_canvas_upscale_if_needed(
            background=background,
            context=context,
            scene_dir=scene_dir,
            fx_handle=handle,
            prompt=(background_prompt or "").strip(),
            negative_prompt=(background_negative_prompt or "").strip(),
        )
    finally:
        unload_model(context.background_generator_model)


@task(name="discoverex-generate-background-detail-reconstruct", persist_result=False)
def _background_detail_reconstruct_stage(
    *,
    context: AppContextLike,
    scene_dir: Path,
    background: Background,
    background_prompt: str | None,
    background_negative_prompt: str | None,
) -> Background:
    handle = context.background_generator_model.load(
        context.model_versions.background_generator
    )
    try:
        return apply_background_detail_reconstruction_if_needed(
            background=background,
            context=context,
            scene_dir=scene_dir,
            fx_handle=handle,
            prompt=(background_prompt or "").strip(),
            negative_prompt=(background_negative_prompt or "").strip(),
        )
    finally:
        unload_model(context.background_generator_model)


@task(name="discoverex-generate-regions", persist_result=False)
def _generate_regions_stage(
    *,
    context: AppContextLike,
    background: Background,
    scene_dir: Path,
    object_prompt: str,
    object_negative_prompt: str,
) -> tuple[list[Any], list[RegionPromptRecord]]:
    # 1. Detect regions (sequential load)
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
        regions_to_process = build_candidate_regions(boxes)
    finally:
        unload_model(context.hidden_region_model)

    object_handle = context.object_generator_model.load(
        context.model_versions.object_generator
    )
    try:
        generated_objects = generate_region_objects(
            context=context,
            scene_dir=scene_dir,
            regions=regions_to_process,
            object_handle=object_handle,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
    finally:
        unload_model(context.object_generator_model)

    # 2. Blend generated objects into regions (sequential load)
    inpaint_handle = context.inpaint_model.load(context.model_versions.inpaint)
    try:
        return generate_regions(
            context=context,
            background=background,
            scene_dir=scene_dir,
            regions=regions_to_process,
            generated_objects=generated_objects,
            inpaint_handle=inpaint_handle,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
    finally:
        unload_model(context.inpaint_model)


@task(name="discoverex-generate-scene", persist_result=False)
def _build_scene_stage(
    *,
    context: AppContextLike,
    background: Background,
    regions: list[Any],
    run_ids: RunIds,
) -> Scene:
    return build_scene(
        background=background,
        regions=regions,
        model_versions=context.model_versions.model_dump(mode="python"),
        runtime_cfg=context.runtime,
        run_ids=run_ids,
    )


@task(name="discoverex-generate-compose", persist_result=False)
def _compose_scene_stage(
    *,
    context: AppContextLike,
    background_asset_ref: str,
    scene_dir: Path,
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


@task(name="discoverex-generate-verify", persist_result=False)
def _verify_scene_stage(*, context: AppContextLike, scene: Scene) -> Scene:
    perception_handle = context.perception_model.load(context.model_versions.perception)
    try:
        verify_scene(scene=scene, context=context, perception_handle=perception_handle)
    finally:
        unload_model(context.perception_model)
    scene.meta.updated_at = datetime.now(timezone.utc)
    return scene


@task(name="discoverex-generate-persist", persist_result=False)
def _persist_scene_outputs(
    *,
    context: AppContextLike,
    scene_dir: Path,
    scene: Scene,
    background_prompt_record: PromptStageRecord,
    region_prompt_records: list[RegionPromptRecord],
    object_prompt: str,
    object_negative_prompt: str,
    final_prompt: str,
    final_negative_prompt: str,
    fx_input_ref: str,
    prompt_bundle_output_ref: str,
    composite_artifact: Path | None,
) -> Path:
    prompt_bundle = PromptBundle(
        input_mode=background_prompt_record.mode,
        background=background_prompt_record.model_copy(
            update={
                "output_ref": (
                    background_prompt_record.output_ref or prompt_bundle_output_ref
                )
            }
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
    return saved_dir


def _finalize_layers(scene: Scene, background: Background, fx_input_ref: str) -> Scene:
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
    return scene


@flow(name="discoverex-generate-pipeline", persist_result=False)
def run_generate_flow(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
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
    logger.info(
        "generate flow started background_prompt=%s object_prompt=%s final_prompt=%s",
        bool(background_prompt),
        bool(object_prompt),
        bool(final_prompt),
    )
    context = _build_context.submit(
        config,
        execution_snapshot,
        execution_snapshot_path,
    ).result()
    run_ids = _generate_run_ids.submit().result()
    scene_dir = (
        Path(context.artifacts_root) / "scenes" / run_ids.scene_id / run_ids.version_id
    )
    background, background_prompt_record = _build_background_stage.submit(
        context=context,
        scene_dir=scene_dir,
        background_asset_ref=background_asset_ref or None,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    ).result()
    background = _background_canvas_upscale_stage.submit(
        context=context,
        scene_dir=scene_dir,
        background=background,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    ).result()
    background = _background_detail_reconstruct_stage.submit(
        context=context,
        scene_dir=scene_dir,
        background=background,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    ).result()
    background = _materialize_background_asset.submit(background, scene_dir).result()
    logger.info("generate flow background ready asset_ref=%s", background.asset_ref)
    regions, region_prompt_records = _generate_regions_stage.submit(
        context=context,
        background=background,
        scene_dir=scene_dir,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
    ).result()
    scene = _build_scene_stage.submit(
        context=context,
        background=background,
        regions=regions,
        run_ids=run_ids,
    ).result()

    fx_input_ref = background.asset_ref
    inpaint_ref = background.metadata.get("inpaint_composited_ref")
    if isinstance(inpaint_ref, str) and inpaint_ref:
        fx_input_ref = inpaint_ref

    composite: CompositeResolution = _compose_scene_stage.submit(
        context=context,
        background_asset_ref=fx_input_ref,
        scene_dir=scene_dir,
        final_prompt=final_prompt,
        final_negative_prompt=final_negative_prompt,
    ).result()
    scene.composite.final_image_ref = composite.image_ref
    scene = _finalize_layers(scene, background, fx_input_ref)
    logger.info(
        "generate flow render complete regions=%d final_image=%s",
        len(scene.regions),
        scene.composite.final_image_ref,
    )

    scene = _verify_scene_stage.submit(context=context, scene=scene).result()
    _persist_scene_outputs.submit(
        context=context,
        scene_dir=scene_dir,
        scene=scene,
        background_prompt_record=background_prompt_record,
        region_prompt_records=region_prompt_records,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
        final_prompt=final_prompt,
        final_negative_prompt=final_negative_prompt,
        fx_input_ref=fx_input_ref,
        prompt_bundle_output_ref=background.asset_ref,
        composite_artifact=composite.artifact_path,
    ).result()
    logger.info(
        "generate flow completed scene_id=%s version_id=%s duration=%s",
        scene.meta.scene_id,
        scene.meta.version_id,
        format_seconds(started),
    )
    return build_scene_payload(
        scene,
        config.runtime.artifacts_root,
        str(execution_snapshot_path) if execution_snapshot_path is not None else None,
        getattr(context, "tracking_run_id", None),
    )
