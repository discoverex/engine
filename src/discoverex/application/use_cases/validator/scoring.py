from __future__ import annotations

from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_scene_difficulty,
    integrate_verification_v2,
    resolve_answer,
)
from discoverex.domain.verification import (
    FinalVerification,
    VerificationBundle,
    VerificationResult,
)
from discoverex.models.types import ValidatorInput


def build_verification_bundle(
    data: ValidatorInput,
    *,
    pass_threshold: float,
    weights: ScoringWeights,
) -> VerificationBundle:
    physical, logical, visual = data.physical, data.logical, data.visual
    all_obj_ids: set[str] = (
        set(physical.occlusion_map)
        | set(logical.degree_map)
        | set(visual.sigma_threshold_map)
    )
    max_degree = max((logical.degree_map.get(oid, 0) for oid in all_obj_ids), default=1)
    max_degree = max(max_degree, 1)

    answer_obj_metrics: list[dict[str, float | int]] = []
    per_obj_perception: list[float] = []
    per_obj_logical: list[float] = []

    for obj_id in sorted(all_obj_ids):
        metrics: dict[str, float | int] = {
            "occlusion_ratio": physical.occlusion_map.get(obj_id, 0.0),
            "sigma_threshold": visual.sigma_threshold_map.get(obj_id, 16.0),
            "degree": logical.degree_map.get(obj_id, 0),
            "degree_norm": logical.degree_map.get(obj_id, 0) / max_degree,
            "z_depth_hop": physical.z_depth_hop_map.get(obj_id, 0),
            "neighbor_count": physical.cluster_density_map.get(obj_id, 0),
            "hop": logical.hop_map.get(obj_id, 0),
            "diameter": logical.diameter,
            "drr_slope": visual.drr_slope_map.get(obj_id, 0.0),
        }
        if resolve_answer(metrics):
            answer_obj_metrics.append(metrics)
        p_score, l_score, _ = integrate_verification_v2(metrics, pass_threshold, weights)
        per_obj_perception.append(p_score)
        per_obj_logical.append(l_score)

    avg_perception = (
        sum(per_obj_perception) / len(per_obj_perception) if per_obj_perception else 0.0
    )
    avg_logical = sum(per_obj_logical) / len(per_obj_logical) if per_obj_logical else 0.0
    total_score = avg_perception * weights.total_perception + avg_logical * weights.total_logical
    passed = total_score >= pass_threshold
    difficulty = compute_scene_difficulty(answer_obj_metrics, weights)

    return VerificationBundle(
        perception=VerificationResult(
            score=avg_perception,
            **{"pass": passed},
            signals={
                "sigma_threshold_map": visual.sigma_threshold_map,
                "drr_slope_map": visual.drr_slope_map,
            },
        ),
        logical=VerificationResult(
            score=avg_logical,
            **{"pass": passed},
            signals={
                "degree_map": logical.degree_map,
                "hop_map": logical.hop_map,
                "diameter": logical.diameter,
                "answer_obj_count": len(answer_obj_metrics),
                "scene_difficulty": difficulty,
            },
        ),
        final=FinalVerification(
            total_score=total_score,
            **{"pass": passed},
            failure_reason="" if passed else "difficulty_too_low",
        ),
    )
