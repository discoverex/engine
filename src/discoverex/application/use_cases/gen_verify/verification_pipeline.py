from __future__ import annotations

from discoverex.bootstrap import AppContext
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
    context: AppContext,
    perception_handle: ModelHandle,
) -> None:
    logical = run_logical_verification(
        scene,
        pass_threshold=float(context.thresholds.logical_pass),
    )
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
