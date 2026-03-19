from __future__ import annotations

from discoverex.domain.services.hidden import is_hidden
from discoverex.domain.services.types import ObjectMetrics, SceneNorms
from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_difficulty,
    compute_scene_difficulty,
    integrate_verification_v2,
)
from discoverex.domain.verification import (
    FinalVerification,
    HiddenObjectMeta,
    VerificationBundle,
    VerificationResult,
)
from discoverex.models.types import ValidatorInput


def _build_all_metrics(data: ValidatorInput) -> list[ObjectMetrics]:
    physical, color_edge, logical, visual = (
        data.physical,
        data.color_edge,
        data.logical,
        data.visual,
    )
    all_obj_ids = sorted(
        set(physical.alpha_degree_map) | set(visual.sigma_threshold_map)
    )

    max_visual = max(
        (physical.alpha_degree_map.get(oid, 0) for oid in all_obj_ids), default=1
    )
    max_logical = max(
        (logical.degree_map.get(oid, 0) for oid in all_obj_ids), default=1
    )
    max_combined = max(max_visual + max_logical, 1)

    return [
        {
            "obj_id": oid,
            "visual_degree": physical.alpha_degree_map.get(oid, 0),
            "logical_degree": logical.degree_map.get(oid, 0),
            "degree_norm": (
                physical.alpha_degree_map.get(oid, 0) + logical.degree_map.get(oid, 0)
            )
            / max_combined,
            "cluster_density": physical.cluster_density_map.get(oid, 0),
            "z_depth_hop": physical.z_depth_hop_map.get(oid, 0),
            "hop": logical.hop_map.get(oid, 0),
            "diameter": logical.diameter,
            "sigma_threshold": visual.sigma_threshold_map.get(oid, 16.0),
            "drr_slope": visual.drr_slope_map.get(oid, 0.0),
            "similar_count": visual.similar_count_map.get(oid, 0),
            "similar_distance": visual.similar_distance_map.get(oid, 100.0),
            "color_contrast": color_edge.color_contrast_map.get(oid, 0.0),
            "edge_strength": color_edge.edge_strength_map.get(oid, 0.0),
        }
        for oid in all_obj_ids
    ]


def _compute_scene_norms(metrics: list[ObjectMetrics]) -> SceneNorms:
    def _inv_cc(m: ObjectMetrics) -> float:
        return 1.0 / (float(m["color_contrast"]) + 1.0)

    def _inv_es(m: ObjectMetrics) -> float:
        return 1.0 / (float(m["edge_strength"]) + 1.0)

    return {
        "max_inv_cc": max((_inv_cc(m) for m in metrics), default=1.0) or 1.0,
        "max_inv_es": max((_inv_es(m) for m in metrics), default=1.0) or 1.0,
        "max_hop": max((float(m["z_depth_hop"]) for m in metrics), default=1.0) or 1.0,
        "max_cluster": max((float(m["cluster_density"]) for m in metrics), default=1.0)
        or 1.0,
    }


def build_verification_bundle(
    data: ValidatorInput,
    *,
    weights: ScoringWeights,
    difficulty_min: float = 0.1,
    difficulty_max: float = 0.9,
    hidden_obj_min: int = 3,
) -> VerificationBundle:
    all_metrics = _build_all_metrics(data)
    norms = _compute_scene_norms(all_metrics)
    total_objs = len(all_metrics)

    hidden_list: list[tuple[ObjectMetrics, float, float]] = []
    for m in all_metrics:
        judged, hf, af = is_hidden(
            m, norms, float(m["similar_count"]) / max(total_objs - 1, 1)
        )
        if judged:
            hidden_list.append((m, hf, af))

    answer_obj_count = len(hidden_list)
    hidden_objects: list[HiddenObjectMeta] = []
    per_obj_p, per_obj_l = [], []

    for m, hf, af in hidden_list:
        D_obj = compute_difficulty(m, weights, answer_obj_count)
        p_score, l_score, _ = integrate_verification_v2(m, weights, answer_obj_count)
        per_obj_p.append(p_score)
        per_obj_l.append(l_score)

        signals = {
            "degree_norm": float(m["degree_norm"]),
            "cluster_density_norm": min(
                float(m["cluster_density"]) / norms["max_cluster"], 1.0
            ),
            "hop_diameter": float(m["hop"]) / max(float(m["diameter"]), 1e-6),
            "drr_slope_norm": max(0.0, min(float(m["drr_slope"]), 1.0)),
            "sigma_threshold_norm": 1.0 / max(float(m["sigma_threshold"]), 1e-6),
            "similar_count_norm": min(
                float(m["similar_count"]) / max(answer_obj_count - 1, 1), 1.0
            ),
            "similar_distance_norm": 1.0 / (1.0 + float(m["similar_distance"])),
            "color_contrast_norm": 1.0 / (1.0 + float(m["color_contrast"])),
            "edge_strength_norm": 1.0 / (1.0 + float(m["edge_strength"])),
        }
        hidden_objects.append(
            HiddenObjectMeta(
                obj_id=m["obj_id"],
                human_field=hf,
                ai_field=af,
                D_obj=D_obj,
                difficulty_signals=signals,
            )
        )

    avg_p = sum(per_obj_p) / len(per_obj_p) if per_obj_p else 0.0
    avg_l = sum(per_obj_l) / len(per_obj_l) if per_obj_l else 0.0
    scene_difficulty = compute_scene_difficulty(
        [m for (m, _, _) in hidden_list], weights, answer_obj_count
    )

    passed = (
        answer_obj_count >= hidden_obj_min
        and difficulty_min <= scene_difficulty <= difficulty_max
    )
    reason = ""
    if not passed:
        reason = (
            f"hidden_obj_count={answer_obj_count} < {hidden_obj_min}"
            if answer_obj_count < hidden_obj_min
            else f"scene_difficulty={scene_difficulty:.4f} out of [{difficulty_min}, {difficulty_max}]"
        )

    return VerificationBundle(
        perception=VerificationResult(
            score=avg_p,
            **{"pass": passed},
            signals={
                "sigma_threshold_map": data.visual.sigma_threshold_map,
                "drr_slope_map": data.visual.drr_slope_map,
                "similar_count_map": data.visual.similar_count_map,
                "similar_distance_map": data.visual.similar_distance_map,
                "color_contrast_map": data.color_edge.color_contrast_map,
                "edge_strength_map": data.color_edge.edge_strength_map,
            },
        ),
        logical=VerificationResult(
            score=avg_l,
            **{"pass": passed},
            signals={
                "alpha_degree_map": data.physical.alpha_degree_map,
                "logical_degree_map": data.logical.degree_map,
                "cluster_density_map": data.physical.cluster_density_map,
                "z_depth_hop_map": data.physical.z_depth_hop_map,
                "hop_map": data.logical.hop_map,
                "diameter": data.logical.diameter,
                "answer_obj_count": answer_obj_count,
            },
        ),
        final=FinalVerification(
            total_score=scene_difficulty, **{"pass": passed}, failure_reason=reason
        ),
        scene_difficulty=scene_difficulty,
        hidden_objects=hidden_objects,
    )
