from __future__ import annotations

from discoverex.domain.services.hidden import is_hidden
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


def build_verification_bundle(
    data: ValidatorInput,
    *,
    weights: ScoringWeights,
    difficulty_min: float = 0.1,   # 설계안 §3 MVP 변수
    difficulty_max: float = 0.9,   # 설계안 §3 MVP 변수
    hidden_obj_min: int = 3,       # 설계안 §3
) -> VerificationBundle:
    """설계안 §1~§3 기준 VerificationBundle 생성 (3패스 구조).

    Pass 1 — 씬 전체 기준값 계산 (scene_norms)
    Pass 2 — is_hidden() 판정 (similar_count_norm 임시 기준: total_objs - 1)
    Pass 3 — 최종 스코어링 (corrected similar_count_norm = answer_obj_count - 1)
    """
    physical, color_edge, logical, visual = (
        data.physical,
        data.color_edge,
        data.logical,
        data.visual,
    )
    all_obj_ids: list[str] = sorted(
        set(physical.alpha_degree_map) | set(visual.sigma_threshold_map)
    )

    # degree_norm 정규화 기준: max(visual_degree) + max(logical_degree)
    max_visual_degree = max(
        (physical.alpha_degree_map.get(oid, 0) for oid in all_obj_ids), default=1
    )
    max_logical_degree = max(
        (logical.degree_map.get(oid, 0) for oid in all_obj_ids), default=1
    )
    max_combined = max(max_visual_degree + max_logical_degree, 1)

    def _build_metrics(obj_id: str) -> dict:
        visual_deg = physical.alpha_degree_map.get(obj_id, 0)
        logical_deg = logical.degree_map.get(obj_id, 0)
        combined_deg = visual_deg + logical_deg
        return {
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

    all_metrics = [_build_metrics(oid) for oid in all_obj_ids]

    # ------------------------------------------------------------------
    # Pass 1 — 씬 전체 기준값 계산 (scene_norms)
    # ------------------------------------------------------------------
    def _inv_cc(m: dict) -> float:
        return 1.0 / (float(m["color_contrast"]) + 1.0)

    def _inv_es(m: dict) -> float:
        return 1.0 / (float(m["edge_strength"]) + 1.0)

    max_inv_cc = max((_inv_cc(m) for m in all_metrics), default=1.0) or 1.0
    max_inv_es = max((_inv_es(m) for m in all_metrics), default=1.0) or 1.0
    max_hop = max((float(m["z_depth_hop"]) for m in all_metrics), default=1.0) or 1.0
    max_cluster = max((float(m["cluster_density"]) for m in all_metrics), default=1.0) or 1.0

    scene_norms = {
        "max_inv_cc": max_inv_cc,
        "max_inv_es": max_inv_es,
        "max_hop": max_hop,
        "max_cluster": max_cluster,
    }

    # ------------------------------------------------------------------
    # Pass 2 — is_hidden() 판정 (임시 분모: total_objs - 1)
    # ------------------------------------------------------------------
    total_objs = len(all_metrics)
    hidden_list: list[tuple[dict, float, float]] = []  # (metrics, hf, af)

    for m in all_metrics:
        scn_tmp = float(m["similar_count"]) / max(total_objs - 1, 1)
        judged, hf, af = is_hidden(m, scene_norms, scn_tmp)
        if judged:
            hidden_list.append((m, hf, af))

    answer_obj_count = len(hidden_list)

    # ------------------------------------------------------------------
    # Pass 3 — 최종 스코어링 (corrected similar_count_norm)
    # ------------------------------------------------------------------
    hidden_objects: list[HiddenObjectMeta] = []
    per_obj_perception: list[float] = []
    per_obj_logical: list[float] = []

    for (m, hf, af) in hidden_list:
        similar_count = float(m["similar_count"])
        similar_distance = float(m["similar_distance"])
        color_contrast = float(m["color_contrast"])
        edge_strength = float(m["edge_strength"])
        cluster = float(m["cluster_density"])
        drr_slope = float(m["drr_slope"])
        sigma = max(float(m["sigma_threshold"]), 1e-6)
        hop = float(m["hop"])
        diameter = max(float(m["diameter"]), 1e-6)
        degree_norm = float(m["degree_norm"])

        scn = similar_count / max(answer_obj_count - 1, 1)

        D_obj = compute_difficulty(m, weights, answer_obj_count)
        p_score, l_score, _ = integrate_verification_v2(m, weights, answer_obj_count)
        per_obj_perception.append(p_score)
        per_obj_logical.append(l_score)

        signals: dict[str, float] = {
            "degree_norm": degree_norm,
            "cluster_density_norm": min(cluster / max_cluster, 1.0),
            "hop_diameter": hop / diameter,
            "drr_slope_norm": max(0.0, min(drr_slope, 1.0)),
            "sigma_threshold_norm": 1.0 / sigma,  # σ_min=1.0 → 최댓값 1.0
            "similar_count_norm": min(scn, 1.0),
            "similar_distance_norm": 1.0 / (1.0 + similar_distance),
            "color_contrast_norm": 1.0 / (1.0 + color_contrast),
            "edge_strength_norm": 1.0 / (1.0 + edge_strength),
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

    # hidden 객체 기준 평균 perception/logical 보조 점수
    avg_perception = (
        sum(per_obj_perception) / len(per_obj_perception) if per_obj_perception else 0.0
    )
    avg_logical = (
        sum(per_obj_logical) / len(per_obj_logical) if per_obj_logical else 0.0
    )

    scene_difficulty = compute_scene_difficulty(
        [m for (m, _, _) in hidden_list], weights, answer_obj_count
    )

    # ------------------------------------------------------------------
    # Pass 조건 (설계안 §3)
    # ------------------------------------------------------------------
    passed = (
        answer_obj_count >= hidden_obj_min
        and difficulty_min <= scene_difficulty <= difficulty_max
    )
    failure_reason = ""
    if not passed:
        if answer_obj_count < hidden_obj_min:
            failure_reason = f"hidden_obj_count={answer_obj_count} < {hidden_obj_min}"
        else:
            failure_reason = (
                f"scene_difficulty={scene_difficulty:.4f} "
                f"out of [{difficulty_min}, {difficulty_max}]"
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
            },
        ),
        final=FinalVerification(
            total_score=scene_difficulty,
            **{"pass": passed},
            failure_reason=failure_reason,
        ),
        scene_difficulty=scene_difficulty,
        hidden_objects=hidden_objects,
    )
