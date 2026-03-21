from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.application.use_cases.gen_verify.model_lifecycle import unload_model
from discoverex.application.use_cases.gen_verify.objects import generate_region_objects
from discoverex.config import PipelineConfig
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.orchestrator_contract.worker_runtime import write_worker_artifact_manifest


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
    object_count = max(1, int(args.get("object_count") or 1))
    regions = _build_placeholder_regions(object_count)
    handle = context.object_generator_model.load(context.model_versions.object_generator)
    try:
        generated = generate_region_objects(
            context=context,
            scene_dir=run_state.output_dir,
            regions=regions,
            object_handle=handle,
            object_prompt=str(args.get("object_prompt", "") or ""),
            object_negative_prompt=str(args.get("object_negative_prompt", "") or ""),
            max_vram_gb=_max_vram_gb(args),
        )
    finally:
        unload_model(context.object_generator_model)
    artifact_entries = []
    generated_payload: list[dict[str, Any]] = []
    for region_id, asset in generated.items():
        generated_payload.append(
            {
                "region_id": region_id,
                "candidate_ref": asset.candidate_ref,
                "object_ref": asset.object_ref,
                "object_mask_ref": asset.object_mask_ref,
                "raw_alpha_mask_ref": asset.raw_alpha_mask_ref or "",
                "width": asset.width,
                "height": asset.height,
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
            ]
        )
    write_worker_artifact_manifest(
        artifacts_root=context.artifacts_root,
        artifacts=artifact_entries,
    )
    payload: dict[str, Any] = {
        "status": "completed",
        "job_id": run_state.job_id,
        "output_dir": str(run_state.output_dir),
        "generated_objects": generated_payload,
        "object_count": len(generated_payload),
        "max_vram_gb": _max_vram_gb(args),
    }
    if execution_snapshot_path is not None:
        payload["execution_config"] = str(execution_snapshot_path)
    if getattr(context, "tracking_run_id", None):
        payload["mlflow_run_id"] = str(context.tracking_run_id)
    payload["effective_tracking_uri"] = context.settings.tracking.uri
    return payload


def _build_run_state(*, context: AppContextLike) -> ObjectGenerationRun:
    job_id = f"object-only-{uuid4().hex[:12]}"
    output_dir = Path(context.artifacts_root) / "object_generation" / job_id
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


def _max_vram_gb(args: dict[str, Any]) -> float | None:
    raw = args.get("max_vram_gb")
    if raw is None:
        return None
    value = float(raw)
    return value if value > 0 else None
