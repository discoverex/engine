from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from discoverex.adapters.outbound.io.json_files import write_json_file
from discoverex.application.context import AppContextLike
from discoverex.application.services.tracking import (
    apply_tracking_identity,
    tracking_run_name,
)
from discoverex.application.services.worker_artifacts import (
    write_worker_artifact_manifest,
)
from discoverex.application.use_cases.naturalness_evaluation import (
    evaluate_scene_naturalness,
)
from discoverex.application.use_cases.output_exports import export_output_bundle
from discoverex.artifact_paths import naturalness_json_path
from discoverex.domain.scene import Scene
from discoverex.execution_snapshot import build_tracking_params
from discoverex.runtime_logging import format_seconds, get_logger

from ..worker_artifacts import collect_worker_artifacts

logger = get_logger("discoverex.generate.persistence")


def _to_plain_data(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")  # type: ignore[no-any-return,attr-defined]
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(value)  # type: ignore[arg-type]
    return value


def metadata_dir(saved_dir: Path) -> Path:
    return saved_dir / "metadata"


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
        saved_dir.parent.parent,
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


def _sweep_case_results_dir(*, artifacts_root: str | Path, sweep_id: str) -> Path:
    path = (
        Path(artifacts_root)
        / "experiments"
        / "naturalness_sweeps"
        / sweep_id
        / "cases"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_sweep_case_result(
    *,
    context: AppContextLike,
    scene: Scene,
    naturalness_artifact: Path | None,
) -> Path | None:
    execution_snapshot = getattr(context, "execution_snapshot", None)
    if not isinstance(execution_snapshot, dict):
        return None
    args = execution_snapshot.get("args", {})
    if not isinstance(args, dict):
        return None
    sweep_id = str(args.get("sweep_id", "")).strip()
    scenario_id = str(args.get("scenario_id", "")).strip()
    policy_id = (
        str(args.get("policy_id", "")).strip()
        or str(args.get("variant_id", "")).strip()
        or str(args.get("combo_id", "")).strip()
    )
    if not sweep_id or not scenario_id or not policy_id:
        return None
    metrics = _naturalness_metrics(naturalness_artifact)
    payload = {
        "sweep_id": sweep_id,
        "policy_id": policy_id,
        "scenario_id": scenario_id,
        "combo_id": str(args.get("combo_id", "")).strip(),
        "variant_id": str(args.get("variant_id", "")).strip(),
        "search_stage": str(args.get("search_stage", "")).strip(),
        "flow_run_id": str(context.settings.execution.flow_run_id or "").strip(),
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "failure_reason": scene.verification.final.failure_reason,
        "naturalness_metrics": metrics,
        "naturalness_artifact": str(naturalness_artifact) if naturalness_artifact else "",
        "scene_tags": list(scene.meta.tags),
        "model_versions": dict(scene.meta.model_versions),
        "verification": _to_plain_data(scene.verification),
    }
    target = _sweep_case_results_dir(
        artifacts_root=context.artifacts_root,
        sweep_id=sweep_id,
    ) / (
        f"{policy_id}--{scenario_id}--{scene.meta.scene_id}--{scene.meta.version_id}.json"
    )
    write_json_file(target, payload)
    logger.info(
        "naturalness sweep case result written path=%s policy_id=%s scenario_id=%s",
        target,
        policy_id,
        scenario_id,
    )
    return target


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
    execution_snapshot = getattr(context, "execution_snapshot", None)
    execution_snapshot_path = getattr(context, "execution_snapshot_path", None)
    output_exports = export_output_bundle(
        artifacts_root=context.artifacts_root,
        scene=scene,
    )
    saved_metadata_dir = metadata_dir(saved_dir)
    artifact_entries = collect_worker_artifacts(
        saved_dir,
        [
            ("scene", saved_metadata_dir / "scene.json"),
            ("verification", saved_metadata_dir / "verification.json"),
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
            *[
                (f"output_source_layer/{layer_path.name}", layer_path)
                for layer_path in output_exports.source_layer_paths
            ],
            *[
                (f"output_original/{original_path.relative_to(output_exports.manifest_path.parent).as_posix()}", original_path)
                for original_path in output_exports.original_paths
            ],
            *[
                (
                    f"delivery/{delivery_path.relative_to(output_exports.manifest_path.parent).as_posix()}",
                    delivery_path,
                )
                for delivery_path in output_exports.delivery_paths
            ],
        ],
    )

    tracking_run_id = context.tracker.log_pipeline_run(
        run_name=tracking_run_name(context.settings, "gen_verify"),
        params=apply_tracking_identity(
            {
            **build_tracking_params(execution_snapshot),
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
            context.settings,
        ),
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
    _write_sweep_case_result(
        context=context,
        scene=scene,
        naturalness_artifact=naturalness_artifact,
    )
    return tracking_run_id
