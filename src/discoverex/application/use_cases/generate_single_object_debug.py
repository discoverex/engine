from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

from discoverex.application.context import AppContextLike
from discoverex.application.services.worker_artifacts import write_worker_artifact_manifest
from discoverex.application.use_cases.gen_verify.model_lifecycle import unload_model
from discoverex.application.use_cases.gen_verify.objects import generate_region_objects
from discoverex.application.use_cases.worker_artifacts import collect_worker_artifacts
from discoverex.config import PipelineConfig
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource


@dataclass(frozen=True)
class ObjectGenerationRun:
    job_id: str
    output_dir: Path


@dataclass(frozen=True)
class DebugArtifact:
    export_key: str
    logical_name: str
    path: Path
    description: str
    source_ref: str


def run(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    context: AppContextLike,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    _ = config
    run_state = _build_run_state(context=context)
    regions = [_build_placeholder_region()]
    handle = context.object_generator_model.load(context.model_versions.object_generator)
    try:
        generated = generate_region_objects(
            context=context,
            scene_dir=run_state.output_dir,
            regions=regions,
            object_handle=handle,
            object_prompt=str(args.get("object_prompt", "") or ""),
            object_negative_prompt=str(args.get("object_negative_prompt", "") or ""),
            object_generation_size=max(64, int(args.get("object_generation_size") or 512)),
            max_vram_gb=_max_vram_gb(args),
        )
    finally:
        unload_model(context.object_generator_model)

    asset = generated[regions[0].region_id]
    debug_artifacts = _write_debug_exports(
        output_dir=run_state.output_dir,
        region_id=asset.region_id,
        candidate_ref=Path(asset.candidate_ref),
        sam_object_ref=Path(asset.sam_object_ref or asset.object_ref),
        raw_alpha_mask_ref=Path(asset.raw_alpha_mask_ref or asset.object_mask_ref),
        processed_object_ref=Path(asset.object_ref),
        processed_mask_ref=Path(asset.object_mask_ref),
    )
    manifest_path = _write_output_manifest(
        run_state=run_state,
        asset=asset,
        debug_artifacts=debug_artifacts,
    )
    artifact_entries = collect_worker_artifacts(
        run_state.output_dir,
        [
            ("output_manifest", manifest_path),
            *[(artifact.logical_name, artifact.path) for artifact in debug_artifacts],
            ("execution_config", execution_snapshot_path),
        ],
    )
    write_worker_artifact_manifest(
        artifacts_root=context.artifacts_root,
        artifacts=artifact_entries,
    )

    payload: dict[str, Any] = {
        "status": "completed",
        "job_id": run_state.job_id,
        "output_dir": str(run_state.output_dir),
        "object_count": 1,
        "generated_object": {
            "region_id": asset.region_id,
            "candidate_ref": asset.candidate_ref,
            "sam_object_ref": asset.sam_object_ref,
            "object_ref": asset.object_ref,
            "object_mask_ref": asset.object_mask_ref,
            "raw_alpha_mask_ref": asset.raw_alpha_mask_ref,
            "width": asset.width,
            "height": asset.height,
            "mask_source": asset.mask_source,
        },
        "export_keys": {
            artifact.export_key: str(artifact.path.relative_to(run_state.output_dir))
            for artifact in debug_artifacts
        },
        "output_manifest": str(manifest_path),
        "max_vram_gb": _max_vram_gb(args),
    }
    if execution_snapshot_path is not None:
        payload["execution_config"] = str(execution_snapshot_path)
    if getattr(context, "tracking_run_id", None):
        payload["mlflow_run_id"] = str(context.tracking_run_id)
    payload["effective_tracking_uri"] = context.settings.tracking.uri
    payload["flow_run_id"] = context.settings.execution.flow_run_id
    return payload


def _build_run_state(*, context: AppContextLike) -> ObjectGenerationRun:
    job_id = f"single-object-debug-{uuid4().hex[:12]}"
    output_dir = Path(context.artifacts_root) / "object_debug" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return ObjectGenerationRun(job_id=job_id, output_dir=output_dir)


def _build_placeholder_region() -> Region:
    return Region(
        region_id=f"r-{uuid4().hex[:10]}",
        geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=64.0, h=64.0)),
        role=RegionRole.ANSWER,
        source=RegionSource.MANUAL,
        attributes={"proposal_rank": 1},
        version=1,
    )


def _write_debug_exports(
    *,
    output_dir: Path,
    region_id: str,
    candidate_ref: Path,
    sam_object_ref: Path,
    raw_alpha_mask_ref: Path,
    processed_object_ref: Path,
    processed_mask_ref: Path,
) -> list[DebugArtifact]:
    export_dir = output_dir / "outputs" / "original" / region_id
    export_dir.mkdir(parents=True, exist_ok=True)

    rgb_preview_path = export_dir / "candidate.rgb-preview.png"
    alpha_mask_path = export_dir / "candidate.alpha-mask.png"
    final_rgba_path = export_dir / "candidate.final-rgba.png"
    pre_sam_rgba_path = export_dir / "candidate.pre-sam-rgba.png"
    sam_object_path = export_dir / "sam.object.png"
    raw_alpha_path = export_dir / "sam.raw-alpha-mask.png"
    processed_object_path = export_dir / "processed.object.png"
    processed_mask_path = export_dir / "processed.mask.png"

    with Image.open(candidate_ref).convert("RGBA") as candidate_image:
        candidate_image.convert("RGB").save(rgb_preview_path)
        candidate_image.getchannel("A").save(alpha_mask_path)
        candidate_image.save(final_rgba_path)
        candidate_image.save(pre_sam_rgba_path)

    _copy_if_needed(sam_object_ref, sam_object_path)
    _copy_if_needed(raw_alpha_mask_ref, raw_alpha_path)
    _copy_if_needed(processed_object_ref, processed_object_path)
    _copy_if_needed(processed_mask_ref, processed_mask_path)

    return [
        DebugArtifact(
            export_key="rgb_preview",
            logical_name="debug_rgb_preview",
            path=rgb_preview_path,
            description="alpha removed RGB preview derived from the generator RGBA output",
            source_ref=str(candidate_ref),
        ),
        DebugArtifact(
            export_key="alpha_mask",
            logical_name="debug_alpha_mask",
            path=alpha_mask_path,
            description="alpha-only grayscale image derived from the generator RGBA output",
            source_ref=str(candidate_ref),
        ),
        DebugArtifact(
            export_key="final_rgba",
            logical_name="debug_final_rgba",
            path=final_rgba_path,
            description="final RGBA image emitted by the object generator before SAM masking",
            source_ref=str(candidate_ref),
        ),
        DebugArtifact(
            export_key="pre_sam_rgba",
            logical_name="debug_pre_sam_rgba",
            path=pre_sam_rgba_path,
            description="pre-SAM RGBA checkpoint; currently identical to final_rgba in the LayerDiffuse path",
            source_ref=str(candidate_ref),
        ),
        DebugArtifact(
            export_key="sam_object",
            logical_name="debug_sam_object",
            path=sam_object_path,
            description="SAM or alpha-resolved RGBA object after mask extraction",
            source_ref=str(sam_object_ref),
        ),
        DebugArtifact(
            export_key="raw_alpha_mask",
            logical_name="debug_raw_alpha_mask",
            path=raw_alpha_path,
            description="raw alpha mask preserved from the generated RGBA output",
            source_ref=str(raw_alpha_mask_ref),
        ),
        DebugArtifact(
            export_key="processed_object",
            logical_name="debug_processed_object",
            path=processed_object_path,
            description="processed object image after placement preparation",
            source_ref=str(processed_object_ref),
        ),
        DebugArtifact(
            export_key="processed_mask",
            logical_name="debug_processed_mask",
            path=processed_mask_path,
            description="processed mask after placement preparation",
            source_ref=str(processed_mask_ref),
        ),
    ]


def _copy_if_needed(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return
    shutil.copy2(source, destination)


def _write_output_manifest(
    *,
    run_state: ObjectGenerationRun,
    asset: Any,
    debug_artifacts: list[DebugArtifact],
) -> Path:
    manifest_path = run_state.output_dir / "outputs" / "output_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "flow": "single_object_debug",
        "job_id": run_state.job_id,
        "region_id": asset.region_id,
        "generated_object": {
            "candidate_ref": asset.candidate_ref,
            "sam_object_ref": asset.sam_object_ref,
            "object_ref": asset.object_ref,
            "object_mask_ref": asset.object_mask_ref,
            "raw_alpha_mask_ref": asset.raw_alpha_mask_ref,
            "mask_source": asset.mask_source,
            "width": asset.width,
            "height": asset.height,
        },
        "exports": [
            {
                "export_key": artifact.export_key,
                "logical_name": artifact.logical_name,
                "relative_path": str(artifact.path.relative_to(run_state.output_dir)),
                "description": artifact.description,
                "source_ref": artifact.source_ref,
            }
            for artifact in debug_artifacts
        ],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _max_vram_gb(args: dict[str, Any]) -> float | None:
    raw = args.get("max_vram_gb")
    if raw is None:
        return None
    value = float(raw)
    return value if value > 0 else None
