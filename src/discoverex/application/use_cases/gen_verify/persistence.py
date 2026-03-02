from __future__ import annotations

from pathlib import Path

from discoverex.bootstrap import AppContext
from discoverex.domain.scene import Scene


def save_scene(context: AppContext, scene: Scene) -> Path:
    saved_dir = context.artifact_store.save_scene_bundle(scene)
    context.metadata_store.upsert_scene_metadata(scene)
    return saved_dir


def write_verification_report(
    context: AppContext,
    saved_dir: Path,
    scene: Scene,
) -> Path:
    return context.report_writer.write_verification_report(saved_dir, scene)


def track_run(
    *,
    context: AppContext,
    scene: Scene,
    saved_dir: Path,
    composite_artifact: Path | None,
) -> None:
    artifacts = [saved_dir / "scene.json", saved_dir / "verification.json"]
    if composite_artifact is not None:
        artifacts.append(composite_artifact)

    context.tracker.log_pipeline_run(
        run_name="gen_verify",
        params={
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "pipeline_run_id": scene.meta.pipeline_run_id,
            "config_version": scene.meta.config_version,
            **{
                f"model_version.{key}": value
                for key, value in scene.meta.model_versions.items()
            },
        },
        metrics={
            "logical_score": scene.verification.logical.score,
            "perception_score": scene.verification.perception.score,
            "total_score": scene.verification.final.total_score,
            "pass": 1.0 if scene.verification.final.pass_ else 0.0,
        },
        artifacts=artifacts,
    )
