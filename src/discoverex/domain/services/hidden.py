"""설계안 §1 — 숨어있는 객체 판정 (human_field / ai_field / is_hidden).

이 모듈은 순수 계산만 담당한다. 외부 I/O·모델 의존 없음.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 설계안 §1 가중치 상수
# ---------------------------------------------------------------------------

# human_field 가중치 (합 = 1.0)
# w1=color_contrast, w2=edge_strength, w3=z_depth_hop, w4=cluster_density (필수)
# w5=visual_degree, w6=logical_degree (보조 bool)
HF_W = dict(
    color_contrast=0.25,
    edge_strength=0.20,
    z_depth_hop=0.20,
    cluster_density=0.15,
    visual_degree=0.10,
    logical_degree=0.10,
)

# ai_field 가중치 (합 = 1.0)
# w1=color_contrast, w2=edge_strength, w3=similar_count, w4=drr_slope (필수)
# w5=similar_distance, w6=sigma_threshold, w7=visual_degree (보조 bool)
AF_W = dict(
    color_contrast=0.20,
    edge_strength=0.15,
    similar_count=0.30,
    drr_slope=0.20,
    similar_distance=0.07,
    sigma_threshold=0.05,
    visual_degree=0.03,
)

# 설계안 §1 커트라인: 필수조건 중 최소 가중치 항목의 단독 극단값
# θ_human = w4_human(cluster_density=0.15) × extreme(0.9) = 0.135
# θ_ai    = w4_ai(drr_slope=0.20)          × extreme(0.9) = 0.180
θ_HUMAN: float = 0.135
θ_AI: float = 0.180

# 보조 bool 임계값 (기존 resolve_answer 기준 유지)
_θ_VISUAL_DEGREE: int = 2       # bool(visual_degree ≥ θ)
_θ_LOGICAL_DEGREE: int = 3      # bool(logical_degree ≥ θ)
_θ_SIMILAR_DIST: float = 80.0   # bool(similar_distance ≤ θ)
_θ_SIGMA_INV: float = 0.25      # bool(1/σ ≥ θ) → σ ≤ 4.0


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _safe_div(numerator: float, denominator: float) -> float:
    """분모가 0일 때 0 반환."""
    return numerator / denominator if denominator > 1e-9 else 0.0


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

def human_field(
    obj_metrics: dict[str, Any],
    scene_norms: dict[str, float],
) -> float:
    """설계안 §1 — 인간 혼동 필드 (가중합).

    필수 4항 (실수 정규화값):
        w1 · (1/(color_contrast+ε))_norm
        w2 · (1/(edge_strength+ε))_norm
        w3 · z_depth_hop_norm
        w4 · cluster_density_norm
    보조 2항 (bool):
        w5 · bool(visual_degree ≥ θ)
        w6 · bool(logical_degree ≥ θ)

    Parameters
    ----------
    obj_metrics:
        단일 객체 메트릭 dict.
        키: color_contrast, edge_strength, z_depth_hop(또는 hop), cluster_density,
            visual_degree, logical_degree
    scene_norms:
        씬 전체에서 계산한 정규화 기준값.
        키: max_inv_cc, max_inv_es, max_hop, max_cluster
    """
    cc = float(obj_metrics.get("color_contrast", 0.0))
    es = float(obj_metrics.get("edge_strength", 0.0))
    hop = float(obj_metrics.get("z_depth_hop", obj_metrics.get("hop", 0)))
    cluster = float(obj_metrics.get("cluster_density", 0))
    visual_deg = int(obj_metrics.get("visual_degree", 0))
    logical_deg = int(obj_metrics.get("logical_degree", 0))

    max_inv_cc = scene_norms.get("max_inv_cc", 1.0) or 1.0
    max_inv_es = scene_norms.get("max_inv_es", 1.0) or 1.0
    max_hop = scene_norms.get("max_hop", 1.0) or 1.0
    max_cluster = scene_norms.get("max_cluster", 1.0) or 1.0

    # 필수 4항 정규화
    inv_cc_norm = _safe_div(1.0 / (cc + 1.0), max_inv_cc)
    inv_es_norm = _safe_div(1.0 / (es + 1.0), max_inv_es)
    hop_norm = _safe_div(hop, max_hop)
    cluster_norm = _safe_div(cluster, max_cluster)

    # 보조 2항 bool
    b_visual = 1.0 if visual_deg >= _θ_VISUAL_DEGREE else 0.0
    b_logical = 1.0 if logical_deg >= _θ_LOGICAL_DEGREE else 0.0

    return (
        HF_W["color_contrast"] * inv_cc_norm
        + HF_W["edge_strength"] * inv_es_norm
        + HF_W["z_depth_hop"] * hop_norm
        + HF_W["cluster_density"] * cluster_norm
        + HF_W["visual_degree"] * b_visual
        + HF_W["logical_degree"] * b_logical
    )


def ai_field(
    obj_metrics: dict[str, Any],
    scene_norms: dict[str, float],
    similar_count_norm: float,
) -> float:
    """설계안 §1 — AI 혼동 필드 (가중합).

    필수 4항 (실수 정규화값):
        w1 · (1/(color_contrast+ε))_norm
        w2 · (1/(edge_strength+ε))_norm
        w3 · similar_count_norm
        w4 · drr_slope_norm
    보조 3항 (bool):
        w5 · bool(similar_distance ≤ θ)
        w6 · bool(1/σ_threshold ≥ θ)
        w7 · bool(visual_degree ≥ θ)

    Parameters
    ----------
    similar_count_norm:
        호출자가 계산해서 전달 (순환 방지를 위해 외부 주입).
    """
    cc = float(obj_metrics.get("color_contrast", 0.0))
    es = float(obj_metrics.get("edge_strength", 0.0))
    drr_slope = float(obj_metrics.get("drr_slope", 0.0))
    sigma = max(float(obj_metrics.get("sigma_threshold", 1.0)), 1e-6)
    similar_distance = float(obj_metrics.get("similar_distance", 100.0))
    visual_deg = int(obj_metrics.get("visual_degree", 0))

    max_inv_cc = scene_norms.get("max_inv_cc", 1.0) or 1.0
    max_inv_es = scene_norms.get("max_inv_es", 1.0) or 1.0

    # 필수 4항 정규화
    inv_cc_norm = _safe_div(1.0 / (cc + 1.0), max_inv_cc)
    inv_es_norm = _safe_div(1.0 / (es + 1.0), max_inv_es)
    drr_slope_norm = max(0.0, min(drr_slope, 1.0))   # clip [0, 1]

    # 보조 3항 bool
    b_sim_dist = 1.0 if similar_distance <= _θ_SIMILAR_DIST else 0.0
    b_sigma = 1.0 if (1.0 / sigma) >= _θ_SIGMA_INV else 0.0
    b_visual = 1.0 if visual_deg >= _θ_VISUAL_DEGREE else 0.0

    return (
        AF_W["color_contrast"] * inv_cc_norm
        + AF_W["edge_strength"] * inv_es_norm
        + AF_W["similar_count"] * min(similar_count_norm, 1.0)
        + AF_W["drr_slope"] * drr_slope_norm
        + AF_W["similar_distance"] * b_sim_dist
        + AF_W["sigma_threshold"] * b_sigma
        + AF_W["visual_degree"] * b_visual
    )


def is_hidden(
    obj_metrics: dict[str, Any],
    scene_norms: dict[str, float],
    similar_count_norm: float,
) -> tuple[bool, float, float]:
    """설계안 §1 판정 조건.

    is_hidden(obj) = human_field(obj) ≥ θ_HUMAN  OR  ai_field(obj) ≥ θ_AI

    Returns
    -------
    (판정결과, human_field값, ai_field값)
    """
    hf = human_field(obj_metrics, scene_norms)
    af = ai_field(obj_metrics, scene_norms, similar_count_norm)
    return (hf >= θ_HUMAN or af >= θ_AI), hf, af
