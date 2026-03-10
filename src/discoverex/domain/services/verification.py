from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from discoverex.domain.scene import Scene
from discoverex.domain.verification import FinalVerification, VerificationResult


class ScoringWeights(BaseModel):
    """Phase-4 스코어링 수식의 모든 가중치를 집약한 모델.

    모든 필드는 float 이며 외부에서 주입하거나 WeightFitter 로 최적화할 수 있다.

    설계 원칙
    ----------
    * perception / logical sub-score 는 각자의 가중치 합으로 나누어 정규화하므로
      각 컴포넌트의 최댓값은 1.0 이 된다.
    * total_perception + total_logical = 1.0 이면 total_score 의 최댓값도 1.0.
    * difficulty_* 는 정규화 없이 절댓값을 그대로 사용한다 (D(obj) 스케일 유지).
    """

    # integrate_verification_v2 — perception sub-score
    perception_sigma: float = Field(0.50, ge=0.0)
    perception_drr: float = Field(0.50, ge=0.0)
    # integrate_verification_v2 — logical sub-score
    logical_hop: float = Field(0.55, ge=0.0)
    logical_degree: float = Field(0.45, ge=0.0)
    # integrate_verification_v2 — total 집계 (합이 1.0 이어야 max=1.0)
    total_perception: float = Field(0.45, ge=0.0)
    total_logical: float = Field(0.55, ge=0.0)
    # compute_difficulty D(obj) 항별 가중치 (정규화 없음)
    difficulty_occlusion: float = Field(0.25, ge=0.0)
    difficulty_sigma: float = Field(0.20, ge=0.0)
    difficulty_hop: float = Field(0.20, ge=0.0)
    difficulty_degree: float = Field(0.15, ge=0.0)
    difficulty_drr: float = Field(0.20, ge=0.0)
    difficulty_interaction: float = Field(0.10, ge=0.0)
    # ^ w_ix: occlusion × (hop/diameter) 교호작용 가중치.
    #   현재 WeightFitter 학습 대상 외 (total_score에 미관여, D(obj) 경로 전용).
    #   D(obj) 분포 기반 loss 도입 시 _SCORED_KEYS 편입 가능 (A군 승격 1순위 후보).


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
# Validator pipeline — Phase 4 순수 계산 함수
# 모든 입력은 dict 로 받아 도메인 레이어가 모델 타입에 의존하지 않도록 한다.
# ---------------------------------------------------------------------------


def resolve_answer(obj_metrics: dict[str, Any]) -> bool:
    """5개 은닉 조건 중 2개 이상 충족 시 True 반환.

    obj_metrics 키: occlusion_ratio, sigma_threshold, degree,
                    z_depth_hop, neighbor_count
    """
    conditions: list[bool] = [
        obj_metrics.get("occlusion_ratio", 0.0) > 0.3,
        obj_metrics.get("sigma_threshold", 16.0) <= 4,
        obj_metrics.get("degree", 0) >= 3,
        obj_metrics.get("z_depth_hop", 0) >= 2,
        obj_metrics.get("neighbor_count", 0) >= 3,
    ]
    return sum(1 for cond in conditions if cond) >= 2


def compute_difficulty(
    obj_metrics: dict[str, Any], weights: ScoringWeights | None = None
) -> float:
    """D(obj) 난이도 점수 계산.

    D(obj) = w_occ · occlusion²
           + w_sig · (1 / σ_threshold)
           + w_hop · (hop / diameter)
           + w_deg · degree_norm²
           + w_drr · drr_slope
           + w_ix  · occlusion · (hop / diameter)

    obj_metrics 키: occlusion_ratio, sigma_threshold, hop, diameter,
                    degree_norm, drr_slope
    drr_slope = -slope(log(sigma), CLIP_similarity): 클수록 빨리 소실 = 어려움
    """
    w = weights or ScoringWeights()
    occlusion = float(obj_metrics.get("occlusion_ratio", 0.0))
    sigma = max(float(obj_metrics.get("sigma_threshold", 1.0)), 1e-6)
    hop = float(obj_metrics.get("hop", 0))
    diameter = max(float(obj_metrics.get("diameter", 1.0)), 1e-6)
    degree_n = float(obj_metrics.get("degree_norm", 0.0))
    drr_slope = float(obj_metrics.get("drr_slope", 0.0))

    return (
        w.difficulty_occlusion * occlusion**2
        + w.difficulty_sigma * (1.0 / sigma)
        + w.difficulty_hop * (hop / diameter)
        + w.difficulty_degree * degree_n**2
        + w.difficulty_drr * drr_slope
        + w.difficulty_interaction * occlusion * (hop / diameter)
    )


def compute_scene_difficulty(
    answer_objs: list[dict[str, Any]], weights: ScoringWeights | None = None
) -> float:
    """Scene_Difficulty = (1 / |answer|) · Σ D(obj)  (obj ∈ answer)

    집계 방식: 단순 평균 (의도적 선택)
    "개별 객체의 평균 난이도를 씬 난이도로 본다"는 관점을 채택.
    D(obj) 자체가 neighbor_count·degree를 통해 군집 복잡도를 간접 반영하므로
    answer 수로 추가 보정하면 이중 계상이 될 수 있어 단순 평균 유지.
    MVP 데이터 수집 후 분포 확인으로 재검토.
    """
    if not answer_objs:
        return 0.0
    return sum(compute_difficulty(obj, weights) for obj in answer_objs) / len(
        answer_objs
    )


def integrate_verification_v2(
    obj_metrics: dict[str, Any],
    pass_threshold: float = 0.35,
    weights: ScoringWeights | None = None,
) -> tuple[float, float, float]:
    """오브젝트 하나에 대한 정규화된 perception / logical / total 점수 계산.

    perception = (w_σ · (1/σ) + w_drr · drr_slope) / (w_σ + w_drr)   ∈ [0, ∞)
    logical    = (w_hop · (hop/d) + w_deg · deg²) / (w_hop + w_deg)  ∈ [0, 1]
    total      = perception · w_p + logical · w_l

    drr_slope = -slope(log(sigma), CLIP_similarity): 클수록 빨리 소실 = 어려움.
    각 sub-score 를 자신의 가중치 합으로 나누어 정규화하므로 가중치의 절댓값이
    아닌 비율만이 점수에 영향을 준다. total 의 최댓값은 w_p + w_l 이며,
    두 값의 합이 1.0 이면 total 최댓값도 1.0 이 된다.

    반환: (perception_score, logical_score, total_score)
    """
    w = weights or ScoringWeights()
    sigma = max(float(obj_metrics.get("sigma_threshold", 1.0)), 1e-6)
    drr_slope = float(obj_metrics.get("drr_slope", 0.0))
    hop = float(obj_metrics.get("hop", 0))
    diameter = max(float(obj_metrics.get("diameter", 1.0)), 1e-6)
    degree_n = float(obj_metrics.get("degree_norm", 0.0))

    p_denom = max(w.perception_sigma + w.perception_drr, 1e-9)
    perception = (
        w.perception_sigma * (1.0 / sigma) + w.perception_drr * drr_slope
    ) / p_denom

    l_denom = max(w.logical_hop + w.logical_degree, 1e-9)
    logical = (
        w.logical_hop * (hop / diameter) + w.logical_degree * degree_n**2
    ) / l_denom

    total = perception * w.total_perception + logical * w.total_logical
    return perception, logical, total
