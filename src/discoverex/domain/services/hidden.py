"""설계안 §1 — 숨어있는 객체 판정 (human_field / ai_field / is_hidden).

이 모듈은 순수 계산만 담당한다. 외부 I/O·모델 의존 없음.
"""
from __future__ import annotations

from discoverex.domain.services.types import ObjectMetrics, SceneNorms

# ---------------------------------------------------------------------------
# 설계안 §1 가중치 상수
# ---------------------------------------------------------------------------

# human_field 가중치 (합 = 1.0)
# 필수 3항 (실수 정규화): color_contrast, z_depth_hop, cluster_density
# 보조 3항: visual_degree(bool), logical_degree(bool), edge_strength(실수 정규화)
# edge_strength는 레이어 자체 경계 선명도로 배경 대비 의미가 약해 보조로 변경
HF_W = dict(
    color_contrast=0.35,    # 필수
    z_depth_hop=0.25,       # 필수
    cluster_density=0.15,   # 필수 (최소 가중치 → θ_HUMAN 기준)
    visual_degree=0.10,     # 보조 bool
    logical_degree=0.10,    # 보조 bool
    edge_strength=0.05,     # 보조 실수 정규화
)

# ai_field 가중치 (합 = 1.0)
# 필수 3항 (실수 정규화): similar_count, drr_slope, color_contrast
# 보조 4항: similar_distance(bool), sigma_threshold(bool), visual_degree(bool), edge_strength(실수 정규화)
# edge_strength는 레이어 자체 경계 선명도로 배경 대비 의미가 약해 보조로 변경
AF_W = dict(
    similar_count=0.35,     # 필수
    drr_slope=0.20,         # 필수 (최소 가중치 → θ_AI 기준)
    color_contrast=0.20,    # 필수 (최소 가중치 → θ_AI 기준)
    similar_distance=0.10,  # 보조 bool
    sigma_threshold=0.07,   # 보조 bool
    visual_degree=0.04,     # 보조 bool
    edge_strength=0.04,     # 보조 실수 정규화
)

# 설계안 §1 커트라인: 필수조건 중 최소 가중치 항목의 단독 극단값
# θ_human = w_min_human(cluster_density=0.15) × extreme(0.9) = 0.135
# θ_ai    = w_min_ai(drr_slope=color_contrast=0.20) × extreme(0.9) = 0.180
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
    obj_metrics: ObjectMetrics,
    scene_norms: SceneNorms,
) -> float:
    """설계안 §1 — 인간 혼동 필드 (가중합).

    필수 3항 (실수 정규화값):
        w1 · (1/(color_contrast+ε))_norm
        w2 · z_depth_hop_norm
        w3 · cluster_density_norm
    보조 3항:
        w4 · bool(visual_degree ≥ θ)
        w5 · bool(logical_degree ≥ θ)
        w6 · (1/(edge_strength+ε))_norm  ← 실수 정규화 (배경 대비 의미 약해 보조)
    """
    cc = float(obj_metrics["color_contrast"])
    es = float(obj_metrics["edge_strength"])
    hop = float(obj_metrics["z_depth_hop"])
    cluster = float(obj_metrics["cluster_density"])
    visual_deg = int(obj_metrics["visual_degree"])
    logical_deg = int(obj_metrics["logical_degree"])

    max_inv_cc = scene_norms.get("max_inv_cc", 1.0)
    max_inv_es = scene_norms.get("max_inv_es", 1.0)
    max_hop = scene_norms.get("max_hop", 1.0)
    max_cluster = scene_norms.get("max_cluster", 1.0)

    # 필수 3항 정규화
    inv_cc_norm = _safe_div(1.0 / (cc + 1.0), max_inv_cc)
    hop_norm = _safe_div(hop, max_hop)
    cluster_norm = _safe_div(cluster, max_cluster)

    # 보조 3항 (bool 2 + 실수 1)
    b_visual = 1.0 if visual_deg >= _θ_VISUAL_DEGREE else 0.0
    b_logical = 1.0 if logical_deg >= _θ_LOGICAL_DEGREE else 0.0
    inv_es_norm = _safe_div(1.0 / (es + 1.0), max_inv_es)

    return (
        HF_W["color_contrast"] * inv_cc_norm
        + HF_W["z_depth_hop"] * hop_norm
        + HF_W["cluster_density"] * cluster_norm
        + HF_W["visual_degree"] * b_visual
        + HF_W["logical_degree"] * b_logical
        + HF_W["edge_strength"] * inv_es_norm
    )


def ai_field(
    obj_metrics: ObjectMetrics,
    scene_norms: SceneNorms,
    similar_count_norm: float,
) -> float:
    """설계안 §1 — AI 혼동 필드 (가중합).

    필수 3항 (실수 정규화값):
        w1 · similar_count_norm
        w2 · drr_slope_norm
        w3 · (1/(color_contrast+ε))_norm
    보조 4항:
        w4 · bool(similar_distance ≤ θ)
        w5 · bool(1/σ_threshold ≥ θ)
        w6 · bool(visual_degree ≥ θ)
        w7 · (1/(edge_strength+ε))_norm  ← 실수 정규화 (배경 대비 의미 약해 보조)
    """
    cc = float(obj_metrics["color_contrast"])
    es = float(obj_metrics["edge_strength"])
    drr_slope = float(obj_metrics["drr_slope"])
    sigma = max(float(obj_metrics["sigma_threshold"]), 1e-6)
    similar_distance = float(obj_metrics["similar_distance"])
    visual_deg = int(obj_metrics["visual_degree"])

    max_inv_cc = scene_norms.get("max_inv_cc", 1.0)
    max_inv_es = scene_norms.get("max_inv_es", 1.0)

    # 필수 3항 정규화
    inv_cc_norm = _safe_div(1.0 / (cc + 1.0), max_inv_cc)
    drr_slope_norm = max(0.0, min(drr_slope, 1.0))   # clip [0, 1]

    # 보조 4항 (bool 3 + 실수 1)
    b_sim_dist = 1.0 if similar_distance <= _θ_SIMILAR_DIST else 0.0
    b_sigma = 1.0 if (1.0 / sigma) >= _θ_SIGMA_INV else 0.0
    b_visual = 1.0 if visual_deg >= _θ_VISUAL_DEGREE else 0.0
    inv_es_norm = _safe_div(1.0 / (es + 1.0), max_inv_es)

    return (
        AF_W["similar_count"] * min(similar_count_norm, 1.0)
        + AF_W["drr_slope"] * drr_slope_norm
        + AF_W["color_contrast"] * inv_cc_norm
        + AF_W["similar_distance"] * b_sim_dist
        + AF_W["sigma_threshold"] * b_sigma
        + AF_W["visual_degree"] * b_visual
        + AF_W["edge_strength"] * inv_es_norm
    )


def is_hidden(
    obj_metrics: ObjectMetrics,
    scene_norms: SceneNorms,
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
