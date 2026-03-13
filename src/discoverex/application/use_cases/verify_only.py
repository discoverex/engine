from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from discoverex.application.context import AppContextLike
from discoverex.domain import (
    integrate_verification,
    judge_scene,
    run_logical_verification,
)
from discoverex.domain.scene import Scene
from discoverex.domain.verification import VerificationBundle, VerificationResult
from discoverex.execution_snapshot import build_tracking_params
from discoverex.models.types import PerceptionRequest
from discoverex.orchestrator_contract.worker_runtime import (
    write_worker_artifact_manifest,
)

from .worker_artifacts import collect_worker_artifacts


def _run_perception_verification(
    scene: Scene, confidence: float, pass_threshold: float
) -> VerificationResult:
    signals = {"region_count": len(scene.regions), "model_confidence": confidence}
    return VerificationResult(
        score=confidence, pass_=confidence >= pass_threshold, signals=signals
    )


def run_verify_only(scene: Scene, context: AppContextLike) -> Scene:
    perception_version = scene.meta.model_versions.get(
        "perception", context.model_versions.perception
    )
    handle = context.perception_model.load(perception_version)

    logical = run_logical_verification(
        scene, pass_threshold=float(context.thresholds.logical_pass)
    )
    pred = context.perception_model.predict(
        handle,
        PerceptionRequest(
            image_ref=scene.composite.final_image_ref,
            region_count=len(scene.regions),
            regions=[
                {"region_id": region.region_id, "role": region.role.value}
                for region in scene.regions
            ],
            question_context=scene.goal.goal_type.value,
        ),
    )
    perception = _run_perception_verification(
        scene,
        confidence=float(pred["confidence"]),
        pass_threshold=float(context.thresholds.perception_pass),
    )
    final = integrate_verification(
        logical, perception, pass_threshold=float(context.thresholds.final_pass)
    )

    scene.verification = VerificationBundle(
        logical=logical, perception=perception, final=final
    )
    scene.meta.status = judge_scene(scene)
    scene.meta.pipeline_run_id = f"run-{uuid4().hex[:12]}"
    scene.meta.updated_at = datetime.now(timezone.utc)

    saved_dir = context.artifact_store.save_scene_bundle(scene)
    context.metadata_store.upsert_scene_metadata(scene)

    context.report_writer.write_verification_report(saved_dir=saved_dir, scene=scene)

    scene_artifact = Path(scene.composite.final_image_ref)
    artifact_entries = collect_worker_artifacts(
        saved_dir,
        [
            ("scene", saved_dir / "scene.json"),
            ("verification", saved_dir / "verification.json"),
            ("final_image", scene_artifact if scene_artifact.exists() else None),
            ("execution_config", context.execution_snapshot_path),
        ],
    )
    context.tracker.log_pipeline_run(
        run_name="verify_only",
        params={
            **build_tracking_params(context.execution_snapshot),
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "pipeline_run_id": scene.meta.pipeline_run_id,
            "config_version": scene.meta.config_version,
            **{f"model_version.{k}": v for k, v in scene.meta.model_versions.items()},
        },
        metrics={
            "logical_score": scene.verification.logical.score,
            "perception_score": scene.verification.perception.score,
            "total_score": scene.verification.final.total_score,
            "pass": 1.0 if scene.verification.final.pass_ else 0.0,
        },
        artifacts=[artifact_path for _, artifact_path in artifact_entries],
    )
    write_worker_artifact_manifest(
        artifacts_root=context.artifacts_root,
        artifacts=artifact_entries,
    )
    return scene
