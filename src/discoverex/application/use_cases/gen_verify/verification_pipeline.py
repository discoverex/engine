from __future__ import annotations

from time import perf_counter

from discoverex.application.context import AppContextLike
from discoverex.domain import (
    integrate_verification,
    judge_scene,
    run_logical_verification,
)
from discoverex.domain.scene import Difficulty, Scene
from discoverex.domain.verification import (
    VerificationBundle,
    VerificationResult,
)
from discoverex.models.types import ModelHandle, PerceptionRequest
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from .runtime_metrics import track_stage_vram

logger = get_logger("discoverex.generate.verify")


def run_perception_verification(
    scene: Scene,
    confidence: float,
    pass_threshold: float,
) -> VerificationResult:
    signals = {"region_count": len(scene.regions), "model_confidence": confidence}
    return VerificationResult(
        score=confidence,
        pass_=confidence >= pass_threshold,
        signals=signals,
    )


def verify_scene(
    scene: Scene,
    context: AppContextLike,
    perception_handle: ModelHandle,
) -> None:
    started = perf_counter()
    logger.info(
        "verification started final_image=%s regions=%d",
        scene.composite.final_image_ref,
        len(scene.regions),
    )
    emit_progress_event(
        stage="verification",
        status="started",
        final_image_ref=scene.composite.final_image_ref,
        region_count=len(scene.regions),
    )
    logical = run_logical_verification(
        scene,
        pass_threshold=float(context.thresholds.logical_pass),
    )
    with track_stage_vram(context, "verification"):
        pred = context.perception_model.predict(
            perception_handle,
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
    perception = run_perception_verification(
        scene=scene,
        confidence=float(pred["confidence"]),
        pass_threshold=float(context.thresholds.perception_pass),
    )
    final = integrate_verification(
        logical,
        perception,
        pass_threshold=float(context.thresholds.final_pass),
    )
    scene.verification = VerificationBundle(
        logical=logical,
        perception=perception,
        final=final,
    )
    scene.difficulty = Difficulty(
        estimated_score=round(1.0 - final.total_score, 4),
        source="rule_based",
    )
    scene.meta.status = judge_scene(scene)
    logger.info(
        "verification completed pass=%s total_score=%.4f duration=%s",
        scene.verification.final.pass_,
        scene.verification.final.total_score,
        format_seconds(started),
    )
    emit_progress_event(
        stage="verification",
        status="completed",
        passed=scene.verification.final.pass_,
        total_score=scene.verification.final.total_score,
    )


def verify_scene_regions(
    *,
    scene: Scene,
    context: AppContextLike,
    perception_handle: ModelHandle,
    scene_dir,
) -> None:  # type: ignore[no-untyped-def]
    from pathlib import Path

    from PIL import Image

    image = Image.open(scene.composite.final_image_ref).convert("RGB")
    try:
        for region in scene.regions:
            bbox = region.geometry.bbox
            crop = image.crop(
                (
                    int(round(bbox.x)),
                    int(round(bbox.y)),
                    int(round(bbox.x + bbox.w)),
                    int(round(bbox.y + bbox.h)),
                )
            )
            crop_path = (
                Path(scene_dir) / "assets" / "verification" / f"{region.region_id}.png"
            )
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_path)
            pred = context.perception_model.predict(
                perception_handle,
                PerceptionRequest(
                    image_ref=str(crop_path),
                    region_count=1,
                    regions=[{"region_id": region.region_id, "role": region.role.value}],
                    question_context=scene.goal.goal_type.value,
                ),
            )
            result = run_perception_verification(
                scene=scene,
                confidence=float(pred["confidence"]),
                pass_threshold=float(context.thresholds.perception_pass),
            )
            region.attributes["verify_score"] = result.score
            region.attributes["verify_pass"] = result.pass_
            region.attributes["verify_crop_ref"] = str(crop_path)
    finally:
        image.close()
