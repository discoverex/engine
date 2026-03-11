from __future__ import annotations

from pathlib import Path
from time import perf_counter

from discoverex.application.context import AppContextLike
from discoverex.domain.scene import Scene
from discoverex.execution_snapshot import build_tracking_params
from discoverex.runtime_logging import format_seconds, get_logger

logger = get_logger("discoverex.generate.persistence")


def save_scene(context: AppContextLike, scene: Scene) -> Path:
    started = perf_counter()
    saved_dir = context.artifact_store.save_scene_bundle(scene)
    context.metadata_store.upsert_scene_metadata(scene)
    logger.info(
        "scene bundle saved dir=%s scene_id=%s version_id=%s duration=%s",
        saved_dir,
        scene.meta.scene_id,
        scene.meta.version_id,
        format_seconds(started),
    )
    return saved_dir


def write_verification_report(
    context: AppContextLike,
    saved_dir: Path,
    scene: Scene,
) -> Path:
    started = perf_counter()
    report_path = context.report_writer.write_verification_report(saved_dir, scene)
    logger.info(
        "verification report written path=%s duration=%s",
        report_path,
        format_seconds(started),
    )
    return report_path


def track_run(
    *,
    context: AppContextLike,
    scene: Scene,
    saved_dir: Path,
    composite_artifact: Path | None,
    prompt_bundle_artifact: Path | None = None,
    extra_params: dict[str, str] | None = None,
) -> None:
    started = perf_counter()
    artifacts = [saved_dir / "scene.json", saved_dir / "verification.json"]
    if composite_artifact is not None:
        artifacts.append(composite_artifact)
    if prompt_bundle_artifact is not None:
        artifacts.append(prompt_bundle_artifact)
    if context.execution_snapshot_path is not None:
        artifacts.append(context.execution_snapshot_path)

    context.tracker.log_pipeline_run(
        run_name="gen_verify",
        params={
            **build_tracking_params(context.execution_snapshot),
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "pipeline_run_id": scene.meta.pipeline_run_id,
            "config_version": scene.meta.config_version,
            **{
                f"model_version.{key}": value
                for key, value in scene.meta.model_versions.items()
            },
            **(extra_params or {}),
        },
        metrics={
            "logical_score": scene.verification.logical.score,
            "perception_score": scene.verification.perception.score,
            "total_score": scene.verification.final.total_score,
            "pass": 1.0 if scene.verification.final.pass_ else 0.0,
        },
        artifacts=artifacts,
    )
    logger.info(
        "tracking completed artifacts=%d duration=%s",
        len(artifacts),
        format_seconds(started),
    )
