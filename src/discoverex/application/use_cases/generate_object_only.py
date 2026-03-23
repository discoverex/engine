from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.application.services.tracking import (
    apply_tracking_identity,
    tracking_run_name,
)
from discoverex.application.use_cases.gen_verify.objects.prompts import (
    split_object_prompts,
)
from discoverex.application.use_cases.gen_verify.model_lifecycle import unload_model
from discoverex.application.use_cases.gen_verify.objects import generate_region_objects
from discoverex.application.use_cases.object_quality import (
    evaluate_generated_objects,
    write_contact_sheet,
)
from discoverex.config import PipelineConfig
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.application.services.worker_artifacts import (
    worker_artifact_root,
    write_worker_artifact_manifest,
)
from discoverex.execution_snapshot import build_tracking_params
from .worker_artifacts import collect_worker_artifacts


@dataclass(frozen=True)
class ObjectGenerationRun:
    job_id: str
    output_dir: Path


def run(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    context: AppContextLike,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    run_state = _build_run_state(context=context)
    _ = config
    object_prompt = str(args.get("object_prompt", "") or "")
    object_negative_prompt = str(args.get("object_negative_prompt", "") or "")
    object_base_prompt = str(args.get("object_base_prompt", "") or "")
    object_base_negative_prompt = str(args.get("object_base_negative_prompt", "") or "")
    object_generation_size = max(64, int(args.get("object_generation_size") or 512))
    object_count = _resolve_object_count(args)
    regions = _build_placeholder_regions(object_count)
    handle = context.object_generator_model.load(context.model_versions.object_generator)
    try:
        generated = generate_region_objects(
            context=context,
            scene_dir=run_state.output_dir,
            regions=regions,
            object_handle=handle,
            object_prompt=object_prompt,
            object_negative_prompt=object_negative_prompt,
            object_base_prompt=object_base_prompt,
            object_base_negative_prompt=object_base_negative_prompt,
            object_generation_size=object_generation_size,
            max_vram_gb=_max_vram_gb(args),
        )
    finally:
        unload_model(context.object_generator_model)
    generated_assets = list(generated.values())
    quality = evaluate_generated_objects(
        output_dir=run_state.output_dir,
        object_prompt=object_prompt,
        generated_objects=generated_assets,
    )
    combo_label = _combo_label(
        steps=getattr(context.object_generator_model, "default_num_inference_steps", None),
        guidance=getattr(context.object_generator_model, "default_guidance_scale", None),
        size=object_generation_size,
    )
    gallery_path = write_contact_sheet(
        output_dir=run_state.output_dir,
        evaluation=quality,
        combo_label=combo_label,
        seed=_runtime_seed(context),
    )
    quality_path = _write_quality_report(
        output_dir=run_state.output_dir,
        quality=quality.to_dict(),
    )
    model_attributes = _model_attributes(context)
    artifact_entries = []
    generated_payload: list[dict[str, Any]] = []
    labels = _resolve_object_labels(object_prompt=object_prompt, object_count=len(generated_assets))
    for index, (region_id, asset) in enumerate(generated.items(), start=1):
        generated_payload.append(
            {
                "object_index": index,
                "object_label": labels[index - 1],
                "region_id": region_id,
                "object_prompt": asset.object_prompt,
                "object_negative_prompt": asset.object_negative_prompt,
                "candidate_ref": asset.candidate_ref,
                "object_ref": asset.object_ref,
                "object_mask_ref": asset.object_mask_ref,
                "raw_alpha_mask_ref": asset.raw_alpha_mask_ref or "",
                "width": asset.width,
                "height": asset.height,
                "mask_source": asset.mask_source,
            }
        )
        artifact_entries.extend(
            [
                (f"{region_id}_candidate", Path(asset.candidate_ref)),
                (f"{region_id}_object", Path(asset.object_ref)),
                (f"{region_id}_mask", Path(asset.object_mask_ref)),
                (
                    f"{region_id}_raw_alpha",
                    Path(asset.raw_alpha_mask_ref) if asset.raw_alpha_mask_ref else None,
                ),
                (f"object_{index:02d}", Path(asset.object_ref)),
                (f"mask_{index:02d}", Path(asset.object_mask_ref)),
            ]
        )
    artifact_entries.extend(
        [
            ("object_quality", quality_path),
            ("quality_gallery", gallery_path),
        ]
    )
    case_result_path = _write_sweep_case_result(
        args=args,
        context=context,
        run_state=run_state,
        generated_payload=generated_payload,
        quality=quality.to_dict(),
        quality_path=quality_path,
        gallery_path=gallery_path,
    )
    if case_result_path is not None:
        artifact_entries.append(("quality_case", case_result_path))
    artifact_entries = collect_worker_artifacts(
        run_state.output_dir,
        artifact_entries,
    )
    write_worker_artifact_manifest(
        artifacts_root=_effective_artifacts_root(context),
        artifacts=artifact_entries,
    )
    tracker = getattr(context, "tracker", None)
    if tracker is not None:
        tracking_run_id = tracker.log_pipeline_run(
            run_name=tracking_run_name(context.settings, "object_generation"),
            params=apply_tracking_identity(
                {
                    **build_tracking_params(getattr(context, "execution_snapshot", None)),
                    "job_id": run_state.job_id,
                    "object_prompt": object_prompt,
                    "object_negative_prompt": object_negative_prompt,
                    "object_base_prompt": object_base_prompt,
                    "object_base_negative_prompt": object_base_negative_prompt,
                    "object_generation_size": str(object_generation_size),
                    "object_count": str(len(generated_payload)),
                    "sweep_id": str(args.get("sweep_id", "")).strip(),
                    "policy_id": str(args.get("policy_id", "")).strip(),
                    "scenario_id": str(args.get("scenario_id", "")).strip(),
                    "quality_gallery_ref": str(gallery_path),
                    "quality_case_result": str(case_result_path) if case_result_path else "",
                    **model_attributes,
                },
                context.settings,
            ),
            metrics={
                "object_quality.run_score": float(quality.summary.run_score),
                "object_quality.mean_overall_score": float(quality.summary.mean_overall_score),
                "object_quality.min_overall_score": float(quality.summary.min_overall_score),
                "object_quality.min_laplacian_variance": float(
                    quality.summary.min_laplacian_variance
                ),
                "object_quality.mean_white_balance_error": float(
                    quality.summary.mean_white_balance_error
                ),
                "object_quality.mean_saturation": float(quality.summary.mean_saturation),
                "object_quality.mean_contrast": float(quality.summary.mean_contrast),
            },
            artifacts=[path for _, path in artifact_entries if path is not None],
        )
        context.tracking_run_id = tracking_run_id
    payload: dict[str, Any] = {
        "status": "completed",
        "job_id": run_state.job_id,
        "output_dir": str(run_state.output_dir),
        "generated_objects": generated_payload,
        "object_count": len(generated_payload),
        "max_vram_gb": _max_vram_gb(args),
        "object_quality": quality.to_dict(),
        "object_quality_report": str(quality_path),
        "quality_gallery_ref": str(gallery_path),
        "model_attributes": model_attributes,
    }
    if case_result_path is not None:
        payload["quality_case_result"] = str(case_result_path)
    if execution_snapshot_path is not None:
        payload["execution_config"] = str(execution_snapshot_path)
    if getattr(context, "tracking_run_id", None):
        payload["mlflow_run_id"] = str(context.tracking_run_id)
    payload["effective_tracking_uri"] = context.settings.tracking.uri
    payload["flow_run_id"] = context.settings.execution.flow_run_id
    return payload


def _build_run_state(*, context: AppContextLike) -> ObjectGenerationRun:
    job_id = f"object-only-{uuid4().hex[:12]}"
    output_dir = _effective_artifacts_root(context) / "object_generation" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return ObjectGenerationRun(job_id=job_id, output_dir=output_dir)


def _build_placeholder_regions(count: int) -> list[Region]:
    regions: list[Region] = []
    for index in range(count):
        regions.append(
            Region(
                region_id=f"r-{uuid4().hex[:10]}",
                geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=64.0, h=64.0)),
                role=RegionRole.ANSWER if index == 0 else RegionRole.CANDIDATE,
                source=RegionSource.MANUAL,
                attributes={"proposal_rank": index + 1},
                version=1,
            )
        )
    return regions


def _resolve_object_count(args: dict[str, Any]) -> int:
    prompts = split_object_prompts(str(args.get("object_prompt", "") or ""))
    if prompts:
        return len(prompts)
    return max(1, int(args.get("object_count") or 1))


def _resolve_object_labels(*, object_prompt: str, object_count: int) -> list[str]:
    prompts = split_object_prompts(object_prompt)
    if not prompts:
        return [f"object-{index:02d}" for index in range(1, object_count + 1)]
    if len(prompts) >= object_count:
        return prompts[:object_count]
    return prompts + [prompts[-1]] * (object_count - len(prompts))


def _max_vram_gb(args: dict[str, Any]) -> float | None:
    raw = args.get("max_vram_gb")
    if raw is None:
        return None
    value = float(raw)
    return value if value > 0 else None


def _combo_label(*, steps: object, guidance: object, size: int) -> str:
    parts = [f"size={size}"]
    if isinstance(steps, (int, float)):
        parts.append(f"steps={steps}")
    if isinstance(guidance, (int, float)):
        parts.append(f"guidance={guidance}")
    return " ".join(parts)


def _runtime_seed(context: AppContextLike) -> int | None:
    runtime = getattr(context, "runtime", None)
    model_runtime = getattr(runtime, "model_runtime", None)
    seed = getattr(model_runtime, "seed", None)
    return seed if isinstance(seed, int) else None


def _effective_artifacts_root(context: AppContextLike) -> Path:
    return worker_artifact_root() or Path(context.artifacts_root)


def _model_attributes(context: AppContextLike) -> dict[str, str]:
    object_model = getattr(context, "object_generator_model", None)
    runtime = getattr(context, "runtime", None)
    model_runtime = getattr(runtime, "model_runtime", None)
    return {
        "object_model_version": str(
            getattr(context.model_versions, "object_generator", "") or ""
        ),
        "object_model_target": str(getattr(object_model, "target", "") or ""),
        "object_model_id": str(getattr(object_model, "model_id", "") or ""),
        "object_sampler": str(getattr(object_model, "sampler", "") or ""),
        "object_steps": str(
            getattr(object_model, "default_num_inference_steps", "") or ""
        ),
        "object_guidance_scale": str(
            getattr(object_model, "default_guidance_scale", "") or ""
        ),
        "object_batch_size": str(getattr(object_model, "batch_size", "") or ""),
        "object_offload_mode": str(getattr(model_runtime, "offload_mode", "") or ""),
        "object_device": str(getattr(model_runtime, "device", "") or ""),
        "object_dtype": str(getattr(model_runtime, "dtype", "") or ""),
    }


def _write_quality_report(*, output_dir: Path, quality: dict[str, object]) -> Path:
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    target = metadata_dir / "object-quality.json"
    target.write_text(json.dumps(quality, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return target


def _write_sweep_case_result(
    *,
    args: dict[str, Any],
    context: AppContextLike,
    run_state: ObjectGenerationRun,
    generated_payload: list[dict[str, Any]],
    quality: dict[str, object],
    quality_path: Path,
    gallery_path: Path,
) -> Path | None:
    sweep_id = str(args.get("sweep_id", "")).strip()
    scenario_id = str(args.get("scenario_id", "")).strip()
    policy_id = str(args.get("policy_id", "")).strip() or str(args.get("combo_id", "")).strip()
    if not sweep_id or not scenario_id or not policy_id:
        return None
    cases_dir = (
        _effective_artifacts_root(context)
        / "experiments"
        / "object_generation_sweeps"
        / sweep_id
        / "cases"
    )
    cases_dir.mkdir(parents=True, exist_ok=True)
    target = cases_dir / f"{policy_id}--{scenario_id}--{run_state.job_id}.json"
    payload = {
        "sweep_id": sweep_id,
        "policy_id": policy_id,
        "scenario_id": scenario_id,
        "combo_id": str(args.get("combo_id", "")).strip(),
        "search_stage": str(args.get("search_stage", "")).strip(),
        "flow_run_id": str(context.settings.execution.flow_run_id or "").strip(),
        "job_id": run_state.job_id,
        "status": "completed",
        "seed": getattr(context.runtime.model_runtime, "seed", None),
        "outputs_prefix": str(args.get("outputs_prefix", "")).strip(),
        "model_attributes": _model_attributes(context),
        "generated_objects": generated_payload,
        "object_quality": quality,
        "object_quality_report": str(quality_path),
        "quality_gallery_ref": str(gallery_path),
    }
    target.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return target
