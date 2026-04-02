from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from discoverex.execution_snapshot import update_execution_snapshot
from discoverex.settings import AppSettings
from discoverex.application.use_cases.gen_verify.verification_pipeline import (
    verify_scene_regions,
)
from discoverex.application.use_cases.gen_verify.model_lifecycle import unload_model

from .artifacts import variant_artifact_entries
from .config import variant_config
from .runtime import reset_variant_background, variant_args, variant_run_ids


def execute_variant(
    *,
    variant: dict[str, Any],
    args: dict[str, Any],
    config: Any,
    execution_snapshot: dict[str, Any] | None,
    background: Any,
    candidate_regions: list[Any],
    generated_objects: Any,
    build_context: Callable[..., Any],
    inpaint_regions: Callable[..., Any],
    build_scene: Callable[..., Any],
    compose_scene: Callable[..., Any],
    verify_scene: Callable[..., Any],
    persist_scene_outputs: Callable[..., Any],
    finalize_layers: Callable[..., Any],
    build_scene_payload: Callable[..., dict[str, Any]],
    prepare_scene_id: str,
    background_prompt_record: Any,
    final_prompt: str,
    final_negative_prompt: str,
    object_prompt: str,
    object_negative_prompt: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    variant_id = str(variant["variant_id"])
    variant_overrides = list(variant["overrides"])
    variant_cfg, variant_snapshot, variant_snapshot_path = variant_config(
        base_snapshot=execution_snapshot,
        variant_overrides=variant_overrides,
        fallback_config=config,
    )
    variant_snapshot["args"] = variant_args(args, variant_id=variant_id)
    update_execution_snapshot(variant_snapshot_path, variant_snapshot)
    resolved_settings = variant_snapshot.get("resolved_settings")
    if not isinstance(resolved_settings, dict):
        raise RuntimeError("variant execution requires resolved_settings in snapshot")
    variant_context = build_context(
        AppSettings.model_validate(resolved_settings),
        variant_snapshot,
        variant_snapshot_path,
    )
    run_ids = variant_run_ids(scene_id=prepare_scene_id, variant_id=variant_id)
    scene_dir = Path(variant_context.artifacts_root) / "scenes" / run_ids.scene_id / run_ids.version_id
    variant_background = reset_variant_background(background)
    variant_regions, region_prompt_records = inpaint_regions(
        context=variant_context,
        background=variant_background,
        scene_dir=scene_dir,
        regions=[region.model_copy(deep=True) for region in candidate_regions],
        generated_objects=generated_objects,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
    )
    scene = build_scene(
        context=variant_context,
        background=variant_background,
        regions=variant_regions,
        run_ids=run_ids,
    )
    scene.meta.tags.append(f"variant:{variant_id}")
    fx_input_ref = variant_background.asset_ref
    inpaint_ref = variant_background.metadata.get("inpaint_composited_ref")
    if isinstance(inpaint_ref, str) and inpaint_ref:
        fx_input_ref = inpaint_ref
    composite = compose_scene(
        context=variant_context,
        background_asset_ref=fx_input_ref,
        scene_dir=scene_dir,
        final_prompt=final_prompt,
        final_negative_prompt=final_negative_prompt,
    )
    scene.composite.final_image_ref = composite.image_ref
    scene = verify_scene(context=variant_context, scene=finalize_layers(scene, variant_background, fx_input_ref))
    perception_handle = variant_context.perception_model.load(
        variant_context.model_versions.perception
    )
    try:
        verify_scene_regions(
            scene=scene,
            context=variant_context,
            perception_handle=perception_handle,
            scene_dir=scene_dir,
        )
    finally:
        unload_model(variant_context.perception_model)
    saved_dir = persist_scene_outputs(
        context=variant_context,
        scene_dir=scene_dir,
        scene=scene,
        background_prompt_record=background_prompt_record,
        region_prompt_records=region_prompt_records,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
        final_prompt=final_prompt,
        final_negative_prompt=final_negative_prompt,
        fx_input_ref=fx_input_ref,
        prompt_bundle_output_ref=variant_background.asset_ref,
        composite_artifact=composite.artifact_path,
    )
    payload = build_scene_payload(
        scene,
        artifacts_root=variant_cfg.runtime.artifacts_root,
        execution_config_path=variant_snapshot_path,
        mlflow_run_id=getattr(variant_context, "tracking_run_id", None),
        effective_tracking_uri=variant_context.settings.tracking.uri,
        flow_run_id=variant_context.settings.execution.flow_run_id,
    )
    payload["variant_id"] = variant_id
    payload["saved_dir"] = str(saved_dir)
    return payload, {"variant_id": variant_id, "overrides": variant_overrides, **payload}


def worker_artifact_entries(
    *,
    manifest_path: Path,
    artifacts_root: Path,
    variant_results: list[dict[str, Any]],
) -> list[tuple[str, Path | None]]:
    artifact_entries: list[tuple[str, Path | None]] = [("variant_pack_manifest", manifest_path)]
    for result in variant_results:
        artifact_entries.extend(
            variant_artifact_entries(
                artifacts_root=artifacts_root,
                variant_result=result,
            )
        )
    return artifact_entries
