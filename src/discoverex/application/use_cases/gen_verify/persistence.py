from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from discoverex.adapters.outbound.io.json_files import write_json_file
from discoverex.application.context import AppContextLike
from discoverex.application.use_cases.naturalness_evaluation import (
    evaluate_scene_naturalness,
)
from discoverex.application.use_cases.output_exports import export_output_bundle
from discoverex.artifact_paths import (
    naturalness_json_path,
)
from discoverex.domain.scene import Scene
from discoverex.execution_snapshot import build_tracking_params
from discoverex.orchestrator_contract.worker_runtime import (
    write_worker_artifact_manifest,
)
from discoverex.runtime_logging import format_seconds, get_logger

from ..worker_artifacts import collect_worker_artifacts

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


def write_naturalness_report(saved_dir: Path, scene: Scene) -> Path | None:
    started = perf_counter()
    try:
        evaluation = evaluate_scene_naturalness(scene)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        logger.info("naturalness report skipped reason=%s", exc)
        return None
    report_path = naturalness_json_path(
        saved_dir.parents[3],
        scene.meta.scene_id,
        scene.meta.version_id,
    )
    write_json_file(
        report_path,
        {
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "naturalness": evaluation.to_dict(),
        },
    )
    logger.info(
        "naturalness report written path=%s duration=%s",
        report_path,
        format_seconds(started),
    )
    return report_path


def _naturalness_metrics(report_path: Path | None) -> dict[str, float]:
    if report_path is None or not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    naturalness = payload.get("naturalness", {})
    if not isinstance(naturalness, dict):
        return {}
    summary = naturalness.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    metrics: dict[str, float] = {}
    overall = naturalness.get("overall_score")
    if isinstance(overall, (int, float)):
        metrics["naturalness.overall_score"] = float(overall)
    for source_key, target_key in (
        ("avg_placement_fit", "naturalness.avg_placement_fit"),
        ("avg_seam_visibility", "naturalness.avg_seam_visibility"),
        ("avg_saliency_lift", "naturalness.avg_saliency_lift"),
    ):
        value = summary.get(source_key)
        if isinstance(value, (int, float)):
            metrics[target_key] = float(value)
    return metrics


def track_run(
    *,
    context: AppContextLike,
    scene: Scene,
    saved_dir: Path,
    composite_artifact: Path | None,
    prompt_bundle_artifact: Path | None = None,
    naturalness_artifact: Path | None = None,
    extra_params: dict[str, str] | None = None,
) -> str | None:
    started = perf_counter()
    flow_run_id = context.settings.execution.flow_run_id.strip()
    flow_run_name = context.settings.execution.flow_run_name.strip()
    execution_snapshot = getattr(context, "execution_snapshot", None)
    execution_snapshot_path = getattr(context, "execution_snapshot_path", None)
    output_exports = export_output_bundle(
        artifacts_root=context.artifacts_root,
        scene=scene,
    )
    artifact_entries = collect_worker_artifacts(
        saved_dir,
        [
            ("scene", saved_dir / "scene.json"),
            ("verification", saved_dir / "verification.json"),
            ("naturalness", naturalness_artifact),
            ("composite", composite_artifact),
            ("prompt_bundle", prompt_bundle_artifact),
            ("lottie", output_exports.lottie_path),
            ("output_manifest", output_exports.manifest_path),
            ("execution_config", execution_snapshot_path),
            *[
                (f"output_layer/{layer_path.name}", layer_path)
                for layer_path in output_exports.layer_paths
            ],
        ],
    )

    tracking_run_id = context.tracker.log_pipeline_run(
        run_name=flow_run_id or "gen_verify",
        params={
            **build_tracking_params(execution_snapshot),
            "prefect.flow_run_id": flow_run_id,
            "prefect.flow_run_name": flow_run_name,
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
            **_naturalness_metrics(naturalness_artifact),
        },
        artifacts=[artifact_path for _, artifact_path in artifact_entries],
    )
    logger.info(
        "tracking completed artifacts=%d duration=%s",
        len(artifact_entries),
        format_seconds(started),
    )
    context.tracking_run_id = tracking_run_id
    write_worker_artifact_manifest(
        artifacts_root=context.artifacts_root,
        artifacts=artifact_entries,
    )
    return tracking_run_id
