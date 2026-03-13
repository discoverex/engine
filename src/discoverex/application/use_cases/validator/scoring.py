from __future__ import annotations

from typing import Any

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
    physical, color_edge, logical, visual = (
        data.physical,
        data.color_edge,
        data.logical,
        data.visual,
    )
    all_obj_ids: set[str] = set(physical.alpha_degree_map) | set(
        visual.sigma_threshold_map
    )

    # degree_norm 정규화 기준: max(visual_degree) + max(logical_degree)
    max_visual_degree = max(
        (physical.alpha_degree_map.get(oid, 0) for oid in all_obj_ids), default=1
    )
    max_logical_degree = max(
        (logical.degree_map.get(oid, 0) for oid in all_obj_ids), default=1
    )
    max_combined = max(max_visual_degree + max_logical_degree, 1)

    answer_obj_metrics: list[dict[str, Any]] = []
    per_obj_perception: list[float] = []
    per_obj_logical: list[float] = []

    for obj_id in sorted(all_obj_ids):
        visual_deg = physical.alpha_degree_map.get(obj_id, 0)
        logical_deg = logical.degree_map.get(obj_id, 0)
        # degree_norm: visual(alpha-overlap) + logical(scene graph) 복합 차수 정규화
        combined_deg = visual_deg + logical_deg
        metrics: dict[str, Any] = {
            "obj_id": obj_id,
            "visual_degree": visual_deg,
            "logical_degree": logical_deg,
            "degree_norm": combined_deg / max_combined,
            "cluster_density": physical.cluster_density_map.get(obj_id, 0),
            "z_depth_hop": physical.z_depth_hop_map.get(obj_id, 0),
            "hop": logical.hop_map.get(obj_id, 0),
            "diameter": logical.diameter,
            "sigma_threshold": visual.sigma_threshold_map.get(obj_id, 16.0),
            "drr_slope": visual.drr_slope_map.get(obj_id, 0.0),
            "similar_count": visual.similar_count_map.get(obj_id, 0),
            "similar_distance": visual.similar_distance_map.get(obj_id, 100.0),
            "color_contrast": color_edge.color_contrast_map.get(obj_id, 0.0),
            "edge_strength": color_edge.edge_strength_map.get(obj_id, 0.0),
        }
        if resolve_answer(metrics, weights.is_hidden_min_conditions):
            answer_obj_metrics.append(metrics)
        p_score, l_score, _ = integrate_verification_v2(
            metrics, pass_threshold, weights
        )
        per_obj_perception.append(p_score)
        per_obj_logical.append(l_score)

    avg_perception = (
        sum(per_obj_perception) / len(per_obj_perception) if per_obj_perception else 0.0
    )
    avg_logical = (
        sum(per_obj_logical) / len(per_obj_logical) if per_obj_logical else 0.0
    )
    total_score = (
        avg_perception * weights.total_perception + avg_logical * weights.total_logical
    )
    passed = total_score >= pass_threshold
    difficulty = compute_scene_difficulty(
        answer_obj_metrics, weights, visual.object_count_map
    )

    # answer_obj_count: Phase 4 object_count_map 기준 answer 오브젝트의 탐지 수 합산
    answer_obj_count = sum(
        visual.object_count_map.get(m["obj_id"], 1) for m in answer_obj_metrics
    )

    return VerificationBundle(
        perception=VerificationResult(
            score=avg_perception,
            **{"pass": passed},
            signals={
                "sigma_threshold_map": visual.sigma_threshold_map,
                "drr_slope_map": visual.drr_slope_map,
                "similar_count_map": visual.similar_count_map,
                "similar_distance_map": visual.similar_distance_map,
                "color_contrast_map": color_edge.color_contrast_map,
                "edge_strength_map": color_edge.edge_strength_map,
            },
        ),
        logical=VerificationResult(
            score=avg_logical,
            **{"pass": passed},
            signals={
                "alpha_degree_map": physical.alpha_degree_map,
                "logical_degree_map": logical.degree_map,
                "cluster_density_map": physical.cluster_density_map,
                "z_depth_hop_map": physical.z_depth_hop_map,
                "hop_map": logical.hop_map,
                "diameter": logical.diameter,
                "answer_obj_count": answer_obj_count,
                "scene_difficulty": difficulty,
            },
        ),
        final=FinalVerification(
            total_score=total_score,
            **{"pass": passed},
            failure_reason="" if passed else "difficulty_too_low",
        ),
    )
