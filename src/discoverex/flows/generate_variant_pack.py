from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from prefect import flow

from discoverex.application.flows.engine_entry import (
    build_execution_snapshot,
    load_pipeline_config,
    normalize_pipeline_config_for_worker_runtime,
    write_execution_snapshot,
)
from discoverex.artifact_paths import (
    naturalness_json_path,
    output_manifest_path,
    prompt_bundle_json_path,
    scene_json_path,
    verification_json_path,
)
from discoverex.application.use_cases.gen_verify.scene_builder import build_scene
from discoverex.application.use_cases.gen_verify.types import RunIds
from discoverex.config import PipelineConfig
from discoverex.execution_snapshot import update_execution_snapshot
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


def _parse_variant_specs(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw = args.get("variant_specs")
    if raw is None:
        raw = args.get("variant_specs_json")
    if raw is None:
        raise ValueError("variant_specs or variant_specs_json is required")
    parsed = raw
    if isinstance(raw, str):
        parsed = json.loads(raw)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("variant specs must decode to a non-empty list")
    variants: list[dict[str, Any]] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise ValueError("each variant spec must be an object")
        variant_id = str(item.get("variant_id", "")).strip() or f"variant-{index:02d}"
        overrides = item.get("overrides", [])
        if not isinstance(overrides, list):
            raise ValueError(f"variant {variant_id} overrides must be a list")
        variants.append(
            {
                "variant_id": variant_id,
                "overrides": [str(value) for value in overrides if str(value).strip()],
            }
        )
    return variants


def _sanitized_variant_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "variant"


def _variant_run_ids(*, scene_id: str, variant_id: str) -> RunIds:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    safe_variant = _sanitized_variant_id(variant_id)[:24]
    return RunIds(
        scene_id=scene_id,
        version_id=f"v-{stamp}-{safe_variant}",
        pipeline_run_id=f"run-{uuid4().hex[:12]}",
    )


def _variant_prepare_dir(*, artifacts_root: Path, scene_id: str, prepare_id: str) -> Path:
    return artifacts_root / "experiments" / "inpaint_variant_pack" / scene_id / prepare_id


def _reset_variant_background(background: Any) -> Any:
    cloned = background.model_copy(deep=True)
    cloned.metadata.pop("inpaint_composited_ref", None)
    cloned.metadata["inpaint_layer_candidates"] = []
    return cloned


def _variant_args(base_args: dict[str, Any], *, variant_id: str) -> dict[str, Any]:
    args = dict(base_args)
    args.pop("variant_specs", None)
    args.pop("variant_specs_json", None)
    args["variant_id"] = variant_id
    return args


def _variant_config(
    *,
    base_snapshot: dict[str, Any] | None,
    variant_overrides: list[str],
    fallback_config: PipelineConfig,
) -> tuple[PipelineConfig, dict[str, Any], Path]:
    if base_snapshot is None:
        raise ValueError("execution_snapshot is required for variant pack flow")
    config_name = str(base_snapshot.get("config_name", "generate") or "generate")
    config_dir = str(base_snapshot.get("config_dir", "conf") or "conf")
    base_overrides = base_snapshot.get("overrides", [])
    if not isinstance(base_overrides, list):
        base_overrides = []
    merged_overrides = [str(item) for item in base_overrides] + variant_overrides
    cfg = load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=merged_overrides,
    )
    cfg = normalize_pipeline_config_for_worker_runtime(cfg)
    cfg.runtime.artifacts_root = fallback_config.runtime.artifacts_root
    snapshot = build_execution_snapshot(
        command="generate",
        args={},
        config_name=config_name,
        config_dir=config_dir,
        overrides=merged_overrides,
        config=cfg,
    )
    snapshot_path = write_execution_snapshot(
        artifacts_root=Path(cfg.runtime.artifacts_root).resolve(),
        command="generate",
        snapshot=snapshot,
    )
    return cfg, snapshot, snapshot_path


def _variant_manifest_path(*, artifacts_root: Path, scene_id: str, prepare_id: str) -> Path:
    path = _variant_prepare_dir(
        artifacts_root=artifacts_root,
        scene_id=scene_id,
        prepare_id=prepare_id,
    )
    path.mkdir(parents=True, exist_ok=True)
    return path / "variant_pack.json"


def _variant_artifact_entries(
    *,
    artifacts_root: Path,
    variant_result: dict[str, Any],
) -> list[tuple[str, Path | None]]:
    scene_id = str(variant_result.get("scene_id", "")).strip()
    version_id = str(variant_result.get("version_id", "")).strip()
    variant_id = str(variant_result.get("variant_id", "")).strip() or "variant"
    if not scene_id or not version_id:
        return []
    output_dir = artifacts_root / "scenes" / scene_id / version_id / "outputs"
    return [
        (f"variant/{variant_id}/scene", scene_json_path(artifacts_root, scene_id, version_id)),
        (
            f"variant/{variant_id}/verification",
            verification_json_path(artifacts_root, scene_id, version_id),
        ),
        (
            f"variant/{variant_id}/naturalness",
            naturalness_json_path(artifacts_root, scene_id, version_id),
        ),
        (
            f"variant/{variant_id}/prompt_bundle",
            prompt_bundle_json_path(artifacts_root, scene_id, version_id),
        ),
        (f"variant/{variant_id}/output_manifest", output_manifest_path(artifacts_root, scene_id, version_id)),
        (f"variant/{variant_id}/lottie", output_dir / "animation.lottie"),
    ]


@flow(name="discoverex-generate-inpaint-variant-pack", persist_result=False)
def run_generate_inpaint_variant_pack_flow(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    background_asset_ref = str(args.get("background_asset_ref", "") or "")
    background_prompt = str(args.get("background_prompt", "") or "")
    background_negative_prompt = str(args.get("background_negative_prompt", "") or "")
    object_prompt = str(args.get("object_prompt", "") or "")
    object_negative_prompt = str(args.get("object_negative_prompt", "") or "")
    final_prompt = str(args.get("final_prompt", "") or "")
    final_negative_prompt = str(args.get("final_negative_prompt", "") or "")
    variant_specs = _parse_variant_specs(args)

    base_context = _build_context.submit(
        config,
        execution_snapshot,
        execution_snapshot_path,
    ).result()
    prepare_ids = _variant_run_ids(scene_id=f"scene-{uuid4().hex[:12]}", variant_id="prepare")
    prepare_dir = _variant_prepare_dir(
        artifacts_root=Path(base_context.artifacts_root),
        scene_id=prepare_ids.scene_id,
        prepare_id=prepare_ids.pipeline_run_id,
    )
    background, background_prompt_record = _build_background_stage.submit(
        context=base_context,
        scene_dir=prepare_dir,
        background_asset_ref=background_asset_ref or None,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    ).result()
    background = _background_canvas_upscale_stage.submit(
        context=base_context,
        scene_dir=prepare_dir,
        background=background,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    ).result()
    background = _background_detail_reconstruct_stage.submit(
        context=base_context,
        scene_dir=prepare_dir,
        background=background,
        background_prompt=background_prompt or None,
        background_negative_prompt=background_negative_prompt or None,
    ).result()
    background = _materialize_background_asset.submit(background, prepare_dir).result()
    candidate_regions = _detect_regions_stage.submit(
        context=base_context,
        background=background,
    ).result()
    generated_objects = _generate_objects_stage.submit(
        context=base_context,
        scene_dir=prepare_dir,
        regions=candidate_regions,
        object_prompt=object_prompt,
        object_negative_prompt=object_negative_prompt,
    ).result()

    variant_results: list[dict[str, Any]] = []
    primary_payload: dict[str, Any] | None = None
    for variant in variant_specs:
        variant_id = str(variant["variant_id"])
        variant_overrides = list(variant["overrides"])
        variant_cfg, variant_snapshot, variant_snapshot_path = _variant_config(
            base_snapshot=execution_snapshot,
            variant_overrides=variant_overrides,
            fallback_config=config,
        )
        variant_args = _variant_args(args, variant_id=variant_id)
        variant_snapshot["args"] = variant_args
        update_execution_snapshot(variant_snapshot_path, variant_snapshot)
        variant_context = _build_context.submit(
            variant_cfg,
            variant_snapshot,
            variant_snapshot_path,
        ).result()
        run_ids = _variant_run_ids(scene_id=prepare_ids.scene_id, variant_id=variant_id)
        scene_dir = (
            Path(variant_context.artifacts_root)
            / "scenes"
            / run_ids.scene_id
            / run_ids.version_id
        )
        variant_background = _reset_variant_background(background)
        variant_regions, region_prompt_records = _inpaint_regions_stage.submit(
            context=variant_context,
            background=variant_background,
            scene_dir=scene_dir,
            regions=[region.model_copy(deep=True) for region in candidate_regions],
            generated_objects=generated_objects,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
        ).result()
        scene = _build_scene_stage.submit(
            context=variant_context,
            background=variant_background,
            regions=variant_regions,
            run_ids=run_ids,
        ).result()
        scene.meta.tags.append(f"variant:{variant_id}")
        fx_input_ref = variant_background.asset_ref
        inpaint_ref = variant_background.metadata.get("inpaint_composited_ref")
        if isinstance(inpaint_ref, str) and inpaint_ref:
            fx_input_ref = inpaint_ref
        composite = _compose_scene_stage.submit(
            context=variant_context,
            background_asset_ref=fx_input_ref,
            scene_dir=scene_dir,
            final_prompt=final_prompt,
            final_negative_prompt=final_negative_prompt,
        ).result()
        scene.composite.final_image_ref = composite.image_ref
        scene = _finalize_layers(scene, variant_background, fx_input_ref)
        scene = _verify_scene_stage.submit(context=variant_context, scene=scene).result()
        saved_dir = _persist_scene_outputs.submit(
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
        ).result()
        payload = build_scene_payload(
            scene,
            variant_cfg.runtime.artifacts_root,
            str(variant_snapshot_path),
            getattr(variant_context, "tracking_run_id", None),
        )
        payload["variant_id"] = variant_id
        payload["saved_dir"] = str(saved_dir)
        lottie_path = (
            Path(variant_cfg.runtime.artifacts_root)
            / "scenes"
            / run_ids.scene_id
            / run_ids.version_id
            / "output"
            / "animation.lottie"
        )
        payload["lottie_path"] = str(lottie_path)
        variant_results.append(
            {
                "variant_id": variant_id,
                "overrides": variant_overrides,
                **payload,
            }
        )
        if primary_payload is None:
            primary_payload = dict(payload)

    manifest_path = _variant_manifest_path(
        artifacts_root=Path(config.runtime.artifacts_root),
        scene_id=prepare_ids.scene_id,
        prepare_id=prepare_ids.pipeline_run_id,
    )
    manifest_path.write_text(
        json.dumps(
            {
                "scene_id": prepare_ids.scene_id,
                "prepare_pipeline_run_id": prepare_ids.pipeline_run_id,
                "prepare_dir": str(prepare_dir),
                "variant_count": len(variant_results),
                "variants": variant_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = primary_payload or {
        "scene_id": prepare_ids.scene_id,
        "version_id": "",
        "scene_json": "",
        "status": "failed",
        "failure_reason": "no_variants_executed",
    }
    payload["variant_pack_manifest"] = str(manifest_path)
    payload["variant_count"] = str(len(variant_results))
    payload["variants"] = variant_results
    if getattr(base_context, "artifacts_root", None):
        from discoverex.orchestrator_contract.worker_runtime import write_worker_artifact_manifest

        artifact_entries: list[tuple[str, Path | None]] = [("variant_pack_manifest", manifest_path)]
        artifacts_root = Path(base_context.artifacts_root)
        for result in variant_results:
            artifact_entries.extend(
                _variant_artifact_entries(
                    artifacts_root=artifacts_root,
                    variant_result=result,
                )
            )
        write_worker_artifact_manifest(
            artifacts_root=artifacts_root,
            artifacts=artifact_entries,
        )
    logger.info(
        "generate inpaint variant pack completed scene_id=%s variants=%d duration=%s",
        prepare_ids.scene_id,
        len(variant_results),
        format_seconds(started),
    )
    return payload
