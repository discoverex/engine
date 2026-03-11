from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from discoverex.domain.scene import Scene
from discoverex.domain.verification import FinalVerification, VerificationResult


class ScoringWeights(BaseModel):
    """Phase 5 스코어링 수식의 모든 가중치를 집약한 모델.

    모든 필드는 float 이며 외부에서 주입하거나 WeightFitter 로 최적화할 수 있다.

    설계 원칙
    ----------
    * perception / logical sub-score 는 각자의 가중치 합으로 나누어 정규화하므로
      각 컴포넌트의 최댓값은 1.0 이 된다.
    * total_perception + total_logical = 1.0 이면 total_score 의 최댓값도 1.0.
    * difficulty_* 는 정규화 없이 절댓값을 그대로 사용한다 (D(obj) 스케일 유지).
    * difficulty_* 의 합이 1.00 이면 D(obj) ∈ [0, 1] 에 가깝게 스케일된다.
    """

    # integrate_verification_v2 — perception sub-score (시각 요소 6항)
    perception_sigma: float = Field(0.10, ge=0.0)          # 블러 내성 (1/σ)
    perception_drr: float = Field(0.15, ge=0.0)            # 블러 소실 속도
    perception_similar_count: float = Field(0.20, ge=0.0)  # 유사 객체 수
    perception_similar_dist: float = Field(0.15, ge=0.0)   # 유사 객체 근접도
    perception_color_contrast: float = Field(0.20, ge=0.0) # 색상 대비 부재
    perception_edge_strength: float = Field(0.20, ge=0.0)  # 경계 불분명도
    # integrate_verification_v2 — logical sub-score (물리+논리 요소 3항)
    logical_hop: float = Field(0.40, ge=0.0)
    logical_degree: float = Field(0.40, ge=0.0)
    logical_cluster: float = Field(0.20, ge=0.0)           # 군집 밀집도
    # integrate_verification_v2 — total 집계 (합이 1.0 이어야 max=1.0)
    total_perception: float = Field(0.45, ge=0.0)
    total_logical: float = Field(0.55, ge=0.0)

    # compute_difficulty D(obj) 항별 가중치 — 합계 1.00
    difficulty_degree: float = Field(0.14, ge=0.0)       # alpha_degree (logical)
    difficulty_cluster: float = Field(0.12, ge=0.0)      # cluster_density
    difficulty_hop: float = Field(0.14, ge=0.0)          # hop / diameter
    difficulty_drr: float = Field(0.14, ge=0.0)          # DRR slope
    difficulty_sigma: float = Field(0.12, ge=0.0)        # 1 / sigma_threshold
    difficulty_similar_count: float = Field(0.11, ge=0.0)  # similar_count
    difficulty_similar_dist: float = Field(0.09, ge=0.0)   # 1 / (1 + similar_distance)
    difficulty_color_contrast: float = Field(0.07, ge=0.0)  # 1 / (1 + color_contrast)
    difficulty_edge_strength: float = Field(0.07, ge=0.0)   # 1 / (1 + edge_strength)

    # resolve_answer 은닉 판정 최소 조건 수
    is_hidden_min_conditions: int = Field(2, ge=1)


def run_logical_verification(scene: Scene, pass_threshold: float) -> VerificationResult:
    answer_count = len(scene.answer.answer_region_ids)
    unique_ok = answer_count == 1 and scene.answer.uniqueness_intent
    region_count = len(scene.regions)
    score = 1.0 if unique_ok else max(0.0, 0.6 - 0.1 * abs(answer_count - 1))
    signals = {
        "answer_count": answer_count,
        "uniqueness_intent": scene.answer.uniqueness_intent,
        "region_count": region_count,
    }
    return VerificationResult(
        score=score,
        pass_=score >= pass_threshold,
        signals=signals,
    )


def integrate_verification(
    logical: VerificationResult,
    perception: VerificationResult,
    pass_threshold: float,
) -> FinalVerification:
    total_score = (logical.score + perception.score) / 2.0
    passed = total_score >= pass_threshold and logical.pass_ and perception.pass_
    failure_reason = "" if passed else "score_or_component_threshold_not_met"
    return FinalVerification(
        total_score=total_score,
        pass_=passed,
        failure_reason=failure_reason,
    )


# ---------------------------------------------------------------------------
# Validator pipeline — Phase 5 순수 계산 함수
# 모든 입력은 dict 로 받아 도메인 레이어가 모델 타입에 의존하지 않도록 한다.
# ---------------------------------------------------------------------------


def resolve_answer(
    obj_metrics: dict[str, Any],
    min_conditions: int = 2,
) -> bool:
    """9개 은닉 조건 중 min_conditions 개 이상 충족 시 True 반환.

    시각적 조건 (6):
        drr_slope      : 블러 소실 속도 — 빨리 소실될수록 찾기 어려움
        similar_count  : 유사 객체 수 많을수록 혼동 유발
        similar_distance: 유사 객체가 가까울수록 혼동 유발
        color_contrast : 배경 대비 낮을수록 묻혀 보임
        edge_strength  : 경계가 불분명할수록 구분 어려움
        visual_degree  : alpha-overlap 연결 차수 높을수록 주변에 묻힘
    물리적 조건 (1):
        cluster_density: 군집 밀집도 높을수록 찾기 어려움
    논리적 조건 (2):
        z_depth_hop    : 레이어 매몰 깊이
        logical_degree : scene graph 논리 연결 차수

    obj_metrics 키: drr_slope, similar_count, similar_distance,
                    color_contrast, edge_strength, visual_degree,
                    cluster_density, z_depth_hop, logical_degree
    """
    conditions: list[bool] = [
        # 시각적 조건
        obj_metrics.get("drr_slope", 0.0) > 0.1,
        obj_metrics.get("similar_count", 0) >= 1,
        obj_metrics.get("similar_distance", 100.0) < 80.0,
        obj_metrics.get("color_contrast", 100.0) <= 30.0,
        obj_metrics.get("edge_strength", 1000.0) <= 400.0,
        obj_metrics.get("visual_degree", 0) >= 2,
        # 물리적 조건
        obj_metrics.get("cluster_density", 0) >= 2,
        # 논리적 조건
        obj_metrics.get("z_depth_hop", 0) >= 2,
        obj_metrics.get("logical_degree", 0) >= 3,
    ]
    return sum(1 for cond in conditions if cond) >= min_conditions


def compute_difficulty(
    obj_metrics: dict[str, Any], weights: ScoringWeights | None = None
) -> float:
    """D(obj) 난이도 점수 계산 (9항 수식, 합계 가중치 = 1.00).

    D(obj) = w_deg  · degree_norm²
           + w_clu  · cluster_norm
           + w_hop  · (hop / diameter)
           + w_drr  · drr_slope
           + w_sig  · (1 / σ_threshold)
           + w_sim  · similar_count_norm
           + w_dst  · (1 / (1 + similar_distance))
           + w_col  · (1 / (1 + color_contrast))
           + w_edg  · (1 / (1 + edge_strength))

    obj_metrics 키: degree_norm, cluster_density, hop, diameter,
                    drr_slope, sigma_threshold, similar_count,
                    similar_distance, color_contrast, edge_strength
    """
    w = weights or ScoringWeights()
    hop = float(obj_metrics.get("hop", 0))
    diameter = max(float(obj_metrics.get("diameter", 1.0)), 1e-6)
    degree_n = float(obj_metrics.get("degree_norm", 0.0))
    drr_slope = float(obj_metrics.get("drr_slope", 0.0))
    sigma = max(float(obj_metrics.get("sigma_threshold", 1.0)), 1e-6)
    cluster = float(obj_metrics.get("cluster_density", 0))
    similar_count = float(obj_metrics.get("similar_count", 0))
    similar_distance = float(obj_metrics.get("similar_distance", 100.0))
    color_contrast = float(obj_metrics.get("color_contrast", 0.0))
    edge_strength = float(obj_metrics.get("edge_strength", 0.0))

    # cluster_norm: 정규화 기준 10 (일반적 씬 최대 밀집도)
    cluster_norm = min(cluster / 10.0, 1.0)
    # similar_count_norm: 정규화 기준 5
    similar_count_norm = min(similar_count / 5.0, 1.0)

    return (
        w.difficulty_degree * degree_n**2
        + w.difficulty_cluster * cluster_norm
        + w.difficulty_hop * (hop / diameter)
        + w.difficulty_drr * drr_slope
        + w.difficulty_sigma * (1.0 / sigma)
        + w.difficulty_similar_count * similar_count_norm
        + w.difficulty_similar_dist * (1.0 / (1.0 + similar_distance))
        + w.difficulty_color_contrast * (1.0 / (1.0 + color_contrast))
        + w.difficulty_edge_strength * (1.0 / (1.0 + edge_strength))
    )


def compute_scene_difficulty(
    answer_objs: list[dict[str, Any]],
    weights: ScoringWeights | None = None,
    object_count_map: dict[str, int] | None = None,
) -> float:
    """Scene_Difficulty = Σ(object_count · D(obj)) / Σ object_count  (obj ∈ answer)

    object_count_map 이 없거나 obj_id 가 없으면 가중치 1 로 처리 (단순 평균 호환).
    obj_id 는 obj_metrics dict 의 'obj_id' 키에서 읽는다.
    """
    if not answer_objs:
        return 0.0
    weighted_sum = 0.0
    total_count = 0
    for obj in answer_objs:
        obj_id = obj.get("obj_id", "")
        count = int((object_count_map or {}).get(obj_id, 1)) if obj_id else 1
        count = max(count, 1)
        weighted_sum += compute_difficulty(obj, weights) * count
        total_count += count
    return weighted_sum / total_count if total_count > 0 else 0.0


def integrate_verification_v2(
    obj_metrics: dict[str, Any],
    pass_threshold: float = 0.35,
    weights: ScoringWeights | None = None,
) -> tuple[float, float, float]:
    """오브젝트 하나에 대한 정규화된 perception / logical / total 점수 계산.

    perception (시각 6항):
        w_σ·(1/σ) + w_drr·drr_slope + w_sim_cnt·sim_cnt_norm
        + w_sim_dist·1/(sim_dist+1) + w_col·1/(color_contrast+1) + w_edg·1/(edge_strength+1)
        / Σw_perception

    logical (물리+논리 3항):
        w_hop·(hop/d) + w_deg·deg² + w_cluster·cluster_norm
        / Σw_logical

    total = perception · w_p + logical · w_l

    각 sub-score 는 자신의 가중치 합으로 나누어 정규화 → 최댓값 ≈ 1.0
    반환: (perception_score, logical_score, total_score)
    """
    w = weights or ScoringWeights()
    sigma = max(float(obj_metrics.get("sigma_threshold", 1.0)), 1e-6)
    drr_slope = float(obj_metrics.get("drr_slope", 0.0))
    similar_count = float(obj_metrics.get("similar_count", 0))
    similar_distance = float(obj_metrics.get("similar_distance", 100.0))
    color_contrast = float(obj_metrics.get("color_contrast", 0.0))
    edge_strength = float(obj_metrics.get("edge_strength", 0.0))
    hop = float(obj_metrics.get("hop", 0))
    diameter = max(float(obj_metrics.get("diameter", 1.0)), 1e-6)
    degree_n = float(obj_metrics.get("degree_norm", 0.0))
    cluster = float(obj_metrics.get("cluster_density", 0))

    # similar_count 정규화 기준 5 (compute_difficulty 와 동일)
    sim_cnt_norm = min(similar_count / 5.0, 1.0)
    cluster_norm = min(cluster / 10.0, 1.0)

    p_denom = max(
        w.perception_sigma + w.perception_drr + w.perception_similar_count
        + w.perception_similar_dist + w.perception_color_contrast + w.perception_edge_strength,
        1e-9,
    )
    perception = (
        w.perception_sigma * (1.0 / sigma)
        + w.perception_drr * drr_slope
        + w.perception_similar_count * sim_cnt_norm
        + w.perception_similar_dist * (1.0 / (1.0 + similar_distance))
        + w.perception_color_contrast * (1.0 / (1.0 + color_contrast))
        + w.perception_edge_strength * (1.0 / (1.0 + edge_strength))
    ) / p_denom

    l_denom = max(w.logical_hop + w.logical_degree + w.logical_cluster, 1e-9)
    logical = (
        w.logical_hop * (hop / diameter) + w.logical_degree * degree_n**2
        + w.logical_cluster * cluster_norm
    ) / l_denom

    total = perception * w.total_perception + logical * w.total_logical
    return perception, logical, total
