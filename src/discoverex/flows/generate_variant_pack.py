from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from prefect import flow

from discoverex.adapters.outbound.io.json_files import write_json_file
from discoverex.application.use_cases.variantpack.artifacts import (
    variant_manifest_path,
    variant_manifest_payload,
)
from discoverex.application.use_cases.variantpack.execute import (
    execute_variant,
    worker_artifact_entries,
)
from discoverex.application.use_cases.variantpack.parse import parse_variant_specs
from discoverex.application.use_cases.variantpack.runtime import (
    variant_prepare_dir,
    variant_run_ids,
)
from discoverex.config import PipelineConfig
from discoverex.orchestrator_contract.worker_runtime import (
    write_worker_artifact_manifest,
)
from discoverex.runtime_logging import format_seconds, get_logger

from .common import build_scene_payload
from .generate import (
    _background_canvas_upscale_stage,
    _background_detail_reconstruct_stage,
    _build_background_stage,
    _build_context,
    _build_scene_stage,
    _compose_scene_stage,
    _detect_regions_stage,
    _finalize_layers,
    _generate_objects_stage,
    _inpaint_regions_stage,
    _materialize_background_asset,
    _persist_scene_outputs,
    _verify_scene_stage,
)

logger = get_logger("discoverex.generate.variant_pack")


def _prepare_shared_inputs(
    *, args: dict[str, Any], config: PipelineConfig, execution_snapshot: dict[str, Any] | None, execution_snapshot_path: Path | None
) -> tuple[Any, Any, Any, Any, list[Any], Any, Any]:
    base_context = _build_context.submit(config, execution_snapshot, execution_snapshot_path).result()
    prepare_ids = variant_run_ids(scene_id=f"scene-{uuid4().hex[:12]}", variant_id="prepare")
    prepare_dir = variant_prepare_dir(
        artifacts_root=Path(base_context.artifacts_root),
        scene_id=prepare_ids.scene_id,
        prepare_id=prepare_ids.pipeline_run_id,
    )
    background, background_prompt_record = _build_background_stage.submit(
        context=base_context,
        scene_dir=prepare_dir,
        background_asset_ref=str(args.get("background_asset_ref", "") or "") or None,
        background_prompt=str(args.get("background_prompt", "") or "") or None,
        background_negative_prompt=str(args.get("background_negative_prompt", "") or "") or None,
    ).result()
    for stage in (_background_canvas_upscale_stage, _background_detail_reconstruct_stage):
        background = stage.submit(
            context=base_context,
            scene_dir=prepare_dir,
            background=background,
            background_prompt=str(args.get("background_prompt", "") or "") or None,
            background_negative_prompt=str(args.get("background_negative_prompt", "") or "") or None,
        ).result()
    background = _materialize_background_asset.submit(background, prepare_dir).result()
    candidate_regions = _detect_regions_stage.submit(context=base_context, background=background).result()
    generated_objects = _generate_objects_stage.submit(
        context=base_context,
        scene_dir=prepare_dir,
        regions=candidate_regions,
        object_prompt=str(args.get("object_prompt", "") or ""),
        object_negative_prompt=str(args.get("object_negative_prompt", "") or ""),
    ).result()
    return (
        base_context,
        prepare_ids,
        prepare_dir,
        background,
        candidate_regions,
        generated_objects,
        background_prompt_record,
    )


@flow(name="discoverex-generate-inpaint-variant-pack", persist_result=False)
def run_generate_inpaint_variant_pack_flow(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    variant_specs = parse_variant_specs(args)
    base_context, prepare_ids, prepare_dir, background, candidate_regions, generated_objects, background_prompt_record = _prepare_shared_inputs(
        args=args,
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    final_prompt = str(args.get("final_prompt", "") or "")
    final_negative_prompt = str(args.get("final_negative_prompt", "") or "")
    object_prompt = str(args.get("object_prompt", "") or "")
    object_negative_prompt = str(args.get("object_negative_prompt", "") or "")
    variant_results: list[dict[str, Any]] = []
    primary_payload: dict[str, Any] | None = None
    for variant in variant_specs:
        payload, result = execute_variant(
            variant=variant,
            args=args,
            config=config,
            execution_snapshot=execution_snapshot,
            background=background,
            candidate_regions=candidate_regions,
            generated_objects=generated_objects,
            build_context=lambda *a: _build_context.submit(*a).result(),
            inpaint_regions=lambda **kw: _inpaint_regions_stage.submit(**kw).result(),
            build_scene=lambda **kw: _build_scene_stage.submit(**kw).result(),
            compose_scene=lambda **kw: _compose_scene_stage.submit(**kw).result(),
            verify_scene=lambda **kw: _verify_scene_stage.submit(**kw).result(),
            persist_scene_outputs=lambda **kw: _persist_scene_outputs.submit(**kw).result(),
            finalize_layers=_finalize_layers,
            build_scene_payload=build_scene_payload,
            prepare_scene_id=prepare_ids.scene_id,
            background_prompt_record=background_prompt_record,
            final_prompt=final_prompt,
            final_negative_prompt=final_negative_prompt,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        )
        primary_payload = payload if primary_payload is None else primary_payload
        variant_results.append(result)
    manifest_path = variant_manifest_path(
        artifacts_root=Path(config.runtime.artifacts_root),
        scene_id=prepare_ids.scene_id,
        prepare_id=prepare_ids.pipeline_run_id,
    )
    write_json_file(
        path=manifest_path,
        payload=variant_manifest_payload(
            scene_id=prepare_ids.scene_id,
            prepare_dir=prepare_dir,
            prepare_pipeline_run_id=prepare_ids.pipeline_run_id,
            variant_results=variant_results,
        ),
    )
    final_payload: dict[str, Any] = primary_payload or {
        "scene_id": prepare_ids.scene_id,
        "version_id": "",
        "scene_json": "",
        "status": "failed",
        "failure_reason": "no_variants_executed",
    }
    final_payload["variant_pack_manifest"] = str(manifest_path)
    final_payload["variant_count"] = str(len(variant_results))
    final_payload["variants"] = variant_results
    if getattr(base_context, "artifacts_root", None):
        write_worker_artifact_manifest(
            artifacts_root=Path(base_context.artifacts_root),
            artifacts=worker_artifact_entries(
                manifest_path=manifest_path,
                artifacts_root=Path(base_context.artifacts_root),
                variant_results=variant_results,
            ),
        )
    logger.info(
        "generate inpaint variant pack completed scene_id=%s variants=%d duration=%s",
        prepare_ids.scene_id,
        len(variant_results),
        format_seconds(started),
    )
    return final_payload
