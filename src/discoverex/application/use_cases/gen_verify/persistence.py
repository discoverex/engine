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
from discoverex.application.use_cases.object_quality import (
    evaluate_generated_objects,
    write_contact_sheet,
)
from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
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
        saved_dir.parent.parent.parent,
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


def _load_naturalness_payload(report_path: Path | None) -> dict[str, Any]:
    if report_path is None or not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _weighted_mean_min(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(0.7 * (sum(values) / len(values)) + 0.3 * min(values), 4)


def _object_label(*, region_attrs: dict[str, Any], region_id: str) -> str:
    for key in ("object_label", "object_prompt_resolved", "object_prompt"):
        value = str(region_attrs.get(key, "") or "").strip()
        if value:
            return value
    return region_id


def _scene_object_assets(scene: Scene) -> list[GeneratedObjectAsset]:
    assets: list[GeneratedObjectAsset] = []
    for region in scene.regions:
        attrs = region.attributes
        object_ref = str(attrs.get("object_image_ref", "") or "").strip()
        mask_ref = str(attrs.get("object_mask_ref", "") or "").strip()
        if not object_ref or not mask_ref:
            continue
        bbox = region.geometry.bbox
        assets.append(
            GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=str(attrs.get("candidate_image_ref", "") or object_ref),
                object_ref=object_ref,
                object_mask_ref=mask_ref,
                raw_alpha_mask_ref=str(attrs.get("raw_alpha_mask_ref", "") or mask_ref),
                original_object_ref=object_ref,
                original_object_mask_ref=mask_ref,
                original_raw_alpha_mask_ref=str(attrs.get("raw_alpha_mask_ref", "") or mask_ref),
                raw_generated_ref=str(attrs.get("raw_generated_image_ref", "") or object_ref),
                sam_object_ref=str(attrs.get("sam_object_image_ref", "") or object_ref),
                sam_mask_ref=str(attrs.get("sam_object_mask_ref", "") or mask_ref),
                mask_source=str(attrs.get("mask_source", "") or "scene_region"),
                width=max(1, int(round(float(bbox.w)))),
                height=max(1, int(round(float(bbox.h)))),
                object_prompt=str(attrs.get("object_prompt_resolved", "") or ""),
                object_negative_prompt=str(
                    attrs.get("object_negative_prompt_resolved", "") or ""
                ),
                object_model_id=str(attrs.get("object_model_id", "") or ""),
                object_sampler=str(attrs.get("object_sampler", "") or ""),
                object_steps=int(attrs.get("object_steps", 0) or 0),
                object_guidance_scale=float(
                    attrs.get("object_guidance_scale", 0.0) or 0.0
                ),
                object_seed=attrs.get("object_seed"),
            )
        )
    return assets


def _evaluate_scene_object_quality(saved_dir: Path, scene: Scene) -> tuple[dict[str, Any], str]:
    assets = _scene_object_assets(scene)
    prompt = " | ".join(
        _object_label(region_attrs=region.attributes, region_id=region.region_id)
        for region in scene.regions
    )
    evaluation = evaluate_generated_objects(
        output_dir=saved_dir,
        object_prompt=prompt,
        generated_objects=assets,
    )
    gallery_ref = ""
    if evaluation.scores:
        seed = None
        for asset in assets:
            if asset.object_seed is not None:
                seed = int(asset.object_seed)
                break
        gallery_ref = str(
            write_contact_sheet(
                output_dir=saved_dir,
                evaluation=evaluation,
                combo_label=scene.meta.scene_id,
                seed=seed,
            )
        )
    return evaluation.to_dict(), gallery_ref


def _object_score_payloads(
    *,
    scene: Scene,
    naturalness_payload: dict[str, Any],
    object_quality: dict[str, Any],
) -> list[dict[str, Any]]:
    naturalness_regions = {}
    naturalness = naturalness_payload.get("naturalness", {})
    if isinstance(naturalness, dict):
        items = naturalness.get("regions", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    naturalness_regions[str(item.get("region_id", "")).strip()] = item
    object_regions = {}
    scores = object_quality.get("scores", [])
    if isinstance(scores, list):
        for item in scores:
            if isinstance(item, dict):
                object_regions[str(item.get("object_ref", "")).strip()] = item
    verify_regions: dict[str, dict[str, Any]] = {}
    for item in getattr(scene.verification, "hidden_objects", []):
        obj_id = str(getattr(item, "obj_id", "") or "").strip()
        if not obj_id:
            continue
        verify_regions[obj_id] = {
            "human_field": float(getattr(item, "human_field", 0.0) or 0.0),
            "ai_field": float(getattr(item, "ai_field", 0.0) or 0.0),
            "D_obj": float(getattr(item, "D_obj", 0.0) or 0.0),
            "difficulty_signals": dict(getattr(item, "difficulty_signals", {}) or {}),
        }
    payloads: list[dict[str, Any]] = []
    for region in scene.regions:
        attrs = region.attributes
        object_ref = str(attrs.get("object_image_ref", "") or "").strip()
        quality = object_regions.get(object_ref, {})
        natural = naturalness_regions.get(region.region_id, {})
        verify = verify_regions.get(region.region_id, {})
        payloads.append(
            {
                "region_id": region.region_id,
                "object_label": _object_label(
                    region_attrs=attrs,
                    region_id=region.region_id,
                ),
                "object_prompt": str(attrs.get("object_prompt", "") or "").strip(),
                "mask_source": str(
                    attrs.get("mask_source")
                    or quality.get("mask_source")
                    or ""
                ).strip(),
                "verify_score": float(attrs.get("verify_score", 0.0) or 0.0),
                "verify_pass": bool(attrs.get("verify_pass", False)),
                "verify_human_field": float(verify.get("human_field", 0.0) or 0.0),
                "verify_ai_field": float(verify.get("ai_field", 0.0) or 0.0),
                "verify_D_obj": float(verify.get("D_obj", 0.0) or 0.0),
                "verify_difficulty_signals": dict(verify.get("difficulty_signals", {}) or {}),
                "naturalness_score": float(
                    natural.get("natural_hidden_score", 0.0) or 0.0
                ),
                "placement_fit": float(natural.get("placement_fit", 0.0) or 0.0),
                "seam_visibility": float(natural.get("seam_visibility", 0.0) or 0.0),
                "saliency_lift": float(natural.get("saliency_lift", 0.0) or 0.0),
                "naturalness_diagnosis_signals": dict(
                    natural.get("diagnosis_signals", {}) or {}
                ),
                "object_quality_score": float(quality.get("overall_score", 0.0) or 0.0),
                "object_quality_subscores": dict(quality.get("subscores", {}) or {}),
                "object_quality_raw_metrics": dict(quality.get("metrics", {}) or {}),
            }
        )
    return payloads


def _float_metrics(prefix: str, payload: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            metrics[f"{prefix}.{key}"] = 1.0 if value else 0.0
            continue
        if isinstance(value, (int, float)):
            metrics[f"{prefix}.{key}"] = float(value)
    return metrics


def _verification_metrics(scene: Scene) -> dict[str, float]:
    metrics = {
        "verify.logical_score": float(scene.verification.logical.score),
        "verify.perception_score": float(scene.verification.perception.score),
        "verify.total_score": float(scene.verification.final.total_score),
        "verify.pass": 1.0 if scene.verification.final.pass_ else 0.0,
        "verify.scene_difficulty": float(scene.verification.scene_difficulty),
        "verify.hidden_object_count": float(len(scene.verification.hidden_objects)),
    }
    metrics.update(_float_metrics("verify.logical.signals", scene.verification.logical.signals))
    metrics.update(
        _float_metrics(
            "verify.perception.signals",
            scene.verification.perception.signals,
        )
    )
    return metrics


def _object_quality_summary_metrics(object_quality: dict[str, Any]) -> dict[str, float]:
    summary = object_quality.get("summary", {})
    if not isinstance(summary, dict):
        return {}
    return _float_metrics("object_quality", summary)


def _representative_scores(
    *,
    scene: Scene,
    naturalness_payload: dict[str, Any],
    object_quality: dict[str, Any],
) -> dict[str, float]:
    object_scores = _object_score_payloads(
        scene=scene,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
    )
    verify_values = [float(item["verify_score"]) for item in object_scores]
    naturalness_values = [float(item["naturalness_score"]) for item in object_scores]
    object_values = [float(item["object_quality_score"]) for item in object_scores]
    verify_repr = _weighted_mean_min(verify_values)
    naturalness_repr = _weighted_mean_min(naturalness_values)
    object_repr = _weighted_mean_min(object_values)
    return {
        "verify_repr": verify_repr,
        "naturalness_repr": naturalness_repr,
        "object_repr": object_repr,
        "composite_repr": round(
            0.5 * verify_repr + 0.3 * naturalness_repr + 0.2 * object_repr,
            4,
        ),
    }


def _sweep_case_results_dir(
    *,
    artifacts_root: str | Path,
    sweep_id: str,
    artifact_namespace: str,
) -> Path:
    path = (
        Path(artifacts_root)
        / "experiments"
        / artifact_namespace
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
    naturalness_payload: dict[str, Any],
    object_quality: dict[str, Any],
    gallery_ref: str,
) -> Path | None:
    execution_snapshot = getattr(context, "execution_snapshot", None)
    if not isinstance(execution_snapshot, dict):
        return None
    args = execution_snapshot.get("args", {})
    if not isinstance(args, dict):
        return None
    sweep_id = str(args.get("sweep_id", "")).strip()
    scenario_id = str(args.get("scenario_id", "")).strip()
    artifact_namespace = (
        str(args.get("sweep_artifact_namespace", "")).strip()
        or "naturalness_sweeps"
    )
    collector_adapter = (
        str(args.get("sweep_collector_adapter", "")).strip()
        or "combined"
    )
    runner_type = str(args.get("sweep_runner_type", "")).strip() or "combined"
    execution_mode = str(args.get("sweep_execution_mode", "")).strip()
    policy_id = (
        str(args.get("policy_id", "")).strip()
        or str(args.get("variant_id", "")).strip()
        or str(args.get("combo_id", "")).strip()
    )
    if not sweep_id or not scenario_id or not policy_id:
        return None
    metrics = _naturalness_metrics(naturalness_artifact)
    object_scores = _object_score_payloads(
        scene=scene,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
    )
    representative_scores = _representative_scores(
        scene=scene,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
    )
    payload = {
        "sweep_id": sweep_id,
        "policy_id": policy_id,
        "scenario_id": scenario_id,
        "combo_id": str(args.get("combo_id", "")).strip(),
        "variant_id": str(args.get("variant_id", "")).strip(),
        "search_stage": str(args.get("search_stage", "")).strip(),
        "sweep_runner_type": runner_type,
        "sweep_collector_adapter": collector_adapter,
        "sweep_artifact_namespace": artifact_namespace,
        "sweep_execution_mode": execution_mode,
        "flow_run_id": str(context.settings.execution.flow_run_id or "").strip(),
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "failure_reason": scene.verification.final.failure_reason,
        "naturalness_metrics": metrics,
        "naturalness_artifact": str(naturalness_artifact) if naturalness_artifact else "",
        "object_quality": object_quality,
        "quality_gallery_ref": gallery_ref,
        "object_scores": object_scores,
        "representative_scores": representative_scores,
        "scene_tags": list(scene.meta.tags),
        "model_versions": dict(scene.meta.model_versions),
        "verification": _to_plain_data(scene.verification),
    }
    target = _sweep_case_results_dir(
        artifacts_root=context.artifacts_root,
        sweep_id=sweep_id,
        artifact_namespace=artifact_namespace,
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
            ("background", output_exports.background_path),
            ("output_manifest", output_exports.manifest_path),
            ("execution_config", execution_snapshot_path),
            *[
                (f"output_object_png/{path.name}", path)
                for path in output_exports.object_png_paths
            ],
            *[
                (f"output_object_lottie/{path.name}", path)
                for path in output_exports.object_lottie_paths
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

    naturalness_payload = _load_naturalness_payload(naturalness_artifact)
    object_quality, gallery_ref = _evaluate_scene_object_quality(saved_dir, scene)
    representative_scores = _representative_scores(
        scene=scene,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
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
            **_verification_metrics(scene),
            **representative_scores,
            **_object_quality_summary_metrics(object_quality),
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
    _track_object_runs(
        context=context,
        scene=scene,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
        parent_run_id=tracking_run_id,
    )
    write_worker_artifact_manifest(
        artifacts_root=context.artifacts_root,
        artifacts=artifact_entries,
    )
    _write_sweep_case_result(
        context=context,
        scene=scene,
        naturalness_artifact=naturalness_artifact,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
        gallery_ref=gallery_ref,
    )
    return tracking_run_id


def _track_object_runs(
    *,
    context: AppContextLike,
    scene: Scene,
    naturalness_payload: dict[str, Any],
    object_quality: dict[str, Any],
    parent_run_id: str | None,
) -> None:
    execution_snapshot = getattr(context, "execution_snapshot", None)
    args = execution_snapshot.get("args", {}) if isinstance(execution_snapshot, dict) else {}
    if not isinstance(args, dict):
        args = {}
    object_scores = _object_score_payloads(
        scene=scene,
        naturalness_payload=naturalness_payload,
        object_quality=object_quality,
    )
    if not object_scores:
        return
    for item in object_scores:
        region_id = str(item["region_id"])
        object_label = str(item["object_label"])
        params = apply_tracking_identity(
            {
                "scene_id": scene.meta.scene_id,
                "version_id": scene.meta.version_id,
                "sweep_id": str(args.get("sweep_id", "") or ""),
                "policy_id": str(args.get("policy_id", "") or ""),
                "scenario_id": str(args.get("scenario_id", "") or ""),
                "variant_id": str(args.get("variant_id", "") or ""),
                "search_stage": str(args.get("search_stage", "") or ""),
                "policy.object_label": object_label,
                "policy.region_id": region_id,
                "policy.object_prompt": str(item.get("object_prompt", "") or ""),
                "policy.mask_source": str(item.get("mask_source", "") or ""),
            },
            context.settings,
        )
        metrics = {
            "verify.object_score": float(item["verify_score"]),
            "verify.object_pass": 1.0 if bool(item["verify_pass"]) else 0.0,
            "verify.human_field": float(item["verify_human_field"]),
            "verify.ai_field": float(item["verify_ai_field"]),
            "verify.D_obj": float(item["verify_D_obj"]),
            "naturalness.object_score": float(item["naturalness_score"]),
            "naturalness.placement_fit": float(item["placement_fit"]),
            "naturalness.seam_visibility": float(item["seam_visibility"]),
            "naturalness.saliency_lift": float(item["saliency_lift"]),
            "object_quality.object_score": float(item["object_quality_score"]),
        }
        for key, value in dict(item["verify_difficulty_signals"]).items():
            if isinstance(value, (int, float)):
                metrics[f"verify.difficulty_signals.{key}"] = float(value)
        for key, value in dict(item["naturalness_diagnosis_signals"]).items():
            if isinstance(value, (int, float)):
                metrics[f"naturalness.diagnosis_signals.{key}"] = float(value)
        for key, value in dict(item["object_quality_subscores"]).items():
            if isinstance(value, (int, float)):
                metrics[f"object_quality.{key}"] = float(value)
        for key, value in dict(item["object_quality_raw_metrics"]).items():
            if isinstance(value, (int, float)):
                metrics[f"object_quality.raw.{key}"] = float(value)
        tags = {
            "run.kind": "object",
            "region_id": region_id,
            "object_label": object_label,
        }
        if parent_run_id:
            tags["mlflow.parentRunId"] = parent_run_id
        context.tracker.log_pipeline_run(
            run_name=f"{scene.meta.scene_id}:{region_id}",
            params=params,
            metrics=metrics,
            artifacts=[],
            tags=tags,
        )
