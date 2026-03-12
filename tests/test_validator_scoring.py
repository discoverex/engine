from __future__ import annotations

import pytest

from discoverex.domain.services.hidden import (
    HF_W,
    AF_W,
    θ_HUMAN,
    θ_AI,
    human_field,
    ai_field,
    is_hidden,
)
from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_difficulty,
    compute_scene_difficulty,
    integrate_verification_v2,
)

# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

_SCENE_NORMS_EQUAL = {
    "max_inv_cc": 1.0,
    "max_inv_es": 1.0,
    "max_hop": 1.0,
    "max_cluster": 1.0,
}


# ---------------------------------------------------------------------------
# human_field  (설계안 §1)
# ---------------------------------------------------------------------------


class TestHumanField:
    def test_all_zero_metrics_returns_nonnegative(self) -> None:
        score = human_field({}, _SCENE_NORMS_EQUAL)
        assert score >= 0.0

    def test_max_inv_cc_contribution(self) -> None:
        """color_contrast=0 → (1/(0+1)) = 1.0 → inv_cc_norm = 1.0."""
        m = {"color_contrast": 0.0}
        score = human_field(m, _SCENE_NORMS_EQUAL)
        assert score >= HF_W["color_contrast"] * 0.99  # 최소 w1 기여

    def test_visual_degree_bool_contribution(self) -> None:
        """visual_degree ≥ 2 → bool 1 → w5 추가."""
        low = human_field({"visual_degree": 1}, _SCENE_NORMS_EQUAL)
        high = human_field({"visual_degree": 2}, _SCENE_NORMS_EQUAL)
        assert high > low

    def test_logical_degree_bool_contribution(self) -> None:
        """logical_degree ≥ 3 → bool 1 → w6 추가."""
        low = human_field({"logical_degree": 2}, _SCENE_NORMS_EQUAL)
        high = human_field({"logical_degree": 3}, _SCENE_NORMS_EQUAL)
        assert high > low

    def test_weight_sum_upper_bound(self) -> None:
        """최대값은 가중치 합 = 1.0 이하여야 한다."""
        m = {
            "color_contrast": 0.0,
            "edge_strength": 0.0,
            "z_depth_hop": 1.0,
            "cluster_density": 1.0,
            "visual_degree": 2,
            "logical_degree": 3,
        }
        score = human_field(m, _SCENE_NORMS_EQUAL)
        assert score <= 1.0 + 1e-9

    def test_scene_norms_scaling(self) -> None:
        """max_inv_cc 가 크면 inv_cc_norm 이 낮아져 score 가 낮아진다."""
        m = {"color_contrast": 0.0}
        score_tight = human_field(m, {"max_inv_cc": 1.0, "max_inv_es": 1.0, "max_hop": 1.0, "max_cluster": 1.0})
        score_loose = human_field(m, {"max_inv_cc": 2.0, "max_inv_es": 1.0, "max_hop": 1.0, "max_cluster": 1.0})
        assert score_tight > score_loose


# ---------------------------------------------------------------------------
# ai_field  (설계안 §1)
# ---------------------------------------------------------------------------


class TestAiField:
    def test_all_zero_metrics_returns_nonnegative(self) -> None:
        score = ai_field({}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert score >= 0.0

    def test_similar_count_norm_contribution(self) -> None:
        """similar_count_norm = 1.0 → w3 추가."""
        low = ai_field({}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        high = ai_field({}, _SCENE_NORMS_EQUAL, similar_count_norm=1.0)
        assert high > low

    def test_drr_slope_clipped(self) -> None:
        """drr_slope > 1.0 → clip 1.0 → 동일 결과."""
        score_1 = ai_field({"drr_slope": 1.0}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        score_2 = ai_field({"drr_slope": 5.0}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert score_1 == pytest.approx(score_2)

    def test_similar_distance_bool_under_threshold(self) -> None:
        """similar_distance ≤ 80.0 → bool 1 → w5 추가."""
        below = ai_field({"similar_distance": 60.0}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        above = ai_field({"similar_distance": 90.0}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert below > above

    def test_sigma_bool_threshold(self) -> None:
        """1/σ ≥ 0.25 → σ ≤ 4.0 → bool 1."""
        low_sigma = ai_field({"sigma_threshold": 2.0}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)  # 1/2=0.5 ≥ 0.25
        high_sigma = ai_field({"sigma_threshold": 8.0}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)  # 1/8=0.125 < 0.25
        assert low_sigma > high_sigma

    def test_visual_degree_bool_contribution(self) -> None:
        low = ai_field({"visual_degree": 1}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        high = ai_field({"visual_degree": 2}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert high > low

    def test_weight_sum_upper_bound(self) -> None:
        m = {
            "color_contrast": 0.0,
            "edge_strength": 0.0,
            "drr_slope": 1.0,
            "similar_distance": 0.0,
            "sigma_threshold": 1.0,
            "visual_degree": 2,
        }
        score = ai_field(m, _SCENE_NORMS_EQUAL, similar_count_norm=1.0)
        assert score <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# is_hidden  (설계안 §1 — 커트라인 판정)
# ---------------------------------------------------------------------------


class TestIsHidden:
    def test_theta_human_cutline(self) -> None:
        """human_field ≥ θ_HUMAN 이면 단독으로 True."""
        # cluster_density=1 → cluster_norm=1.0 (max_cluster=1.0) → w4·1 = 0.15 ≥ θ_HUMAN=0.135
        m = {"cluster_density": 1.0}
        norms = {"max_inv_cc": 1.0, "max_inv_es": 1.0, "max_hop": 1.0, "max_cluster": 1.0}
        judged, hf, af = is_hidden(m, norms, similar_count_norm=0.0)
        assert hf >= θ_HUMAN
        assert judged is True

    def test_theta_ai_cutline(self) -> None:
        """ai_field ≥ θ_AI 이면 단독으로 True."""
        # drr_slope_norm = 1.0 → w4=0.20 ≥ θ_AI=0.180
        m = {"drr_slope": 1.0}
        norms = _SCENE_NORMS_EQUAL
        judged, hf, af = is_hidden(m, norms, similar_count_norm=0.0)
        assert af >= θ_AI
        assert judged is True

    def test_both_below_threshold_is_false(self) -> None:
        """두 field 모두 커트라인 미달이면 False.

        color_contrast=100, edge_strength=100 → inv_cc_norm ≈ 0.0099 (낮음)
        → hf ≈ 0.0045 < θ_HUMAN=0.135, af ≈ 0.0035 < θ_AI=0.180
        """
        m = {
            "color_contrast": 100.0, "edge_strength": 100.0,
            "visual_degree": 0, "logical_degree": 0,
            "z_depth_hop": 0, "cluster_density": 0,
            "drr_slope": 0.0, "similar_distance": 100.0, "sigma_threshold": 16.0,
        }
        judged, hf, af = is_hidden(m, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert judged is False

    def test_returns_three_tuple(self) -> None:
        result = is_hidden({}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert len(result) == 3
        assert isinstance(result[0], bool)
        assert isinstance(result[1], float)
        assert isinstance(result[2], float)

    def test_hf_af_nonnegative(self) -> None:
        _, hf, af = is_hidden({}, _SCENE_NORMS_EQUAL, similar_count_norm=0.0)
        assert hf >= 0.0
        assert af >= 0.0


# ---------------------------------------------------------------------------
# compute_difficulty  (9항 수식, answer_obj_count 파라미터 반영)
# ---------------------------------------------------------------------------


class TestComputeDifficulty:
    def test_zero_metrics_returns_nonnegative(self) -> None:
        score = compute_difficulty({})
        assert score >= 0.0

    def test_high_difficulty_exceeds_low(self) -> None:
        easy = {
            "degree_norm": 0.0, "cluster_density": 0, "hop": 0, "diameter": 4.0,
            "drr_slope": 0.0, "sigma_threshold": 16.0, "similar_count": 0,
            "similar_distance": 100.0, "color_contrast": 100.0, "edge_strength": 100.0,
        }
        hard = {
            "degree_norm": 0.9, "cluster_density": 8, "hop": 3, "diameter": 4.0,
            "drr_slope": 0.25, "sigma_threshold": 1.0, "similar_count": 4,
            "similar_distance": 10.0, "color_contrast": 0.0, "edge_strength": 0.0,
        }
        assert compute_difficulty(hard, answer_obj_count=5) > compute_difficulty(easy, answer_obj_count=5)

    def test_similar_count_norm_uses_answer_obj_count(self) -> None:
        """similar_count / (answer_obj_count - 1)."""
        m = {"similar_count": 3.0}
        # answer_obj_count=4 → norm = 3/3 = 1.0
        # answer_obj_count=7 → norm = 3/6 = 0.5
        score_4 = compute_difficulty(m, answer_obj_count=4)
        score_7 = compute_difficulty(m, answer_obj_count=7)
        assert score_4 > score_7

    def test_drr_slope_clipped_at_1(self) -> None:
        """drr_slope > 1.0 → clip 1.0 → 동일 결과."""
        s1 = compute_difficulty({"drr_slope": 1.0})
        s2 = compute_difficulty({"drr_slope": 10.0})
        assert s1 == pytest.approx(s2)

    def test_sigma_zero_guarded(self) -> None:
        score = compute_difficulty({"sigma_threshold": 0.0})
        assert score >= 0.0

    def test_diameter_zero_guarded(self) -> None:
        score = compute_difficulty({"hop": 2, "diameter": 0.0})
        assert score >= 0.0


# ---------------------------------------------------------------------------
# compute_scene_difficulty  (설계안 §2 — 단순 평균)
# ---------------------------------------------------------------------------


class TestComputeSceneDifficulty:
    def test_empty_list_returns_zero(self) -> None:
        assert compute_scene_difficulty([]) == 0.0

    def test_single_object_equals_compute_difficulty(self) -> None:
        obj = {"sigma_threshold": 4.0, "hop": 2, "diameter": 4.0, "degree_norm": 0.3}
        assert compute_scene_difficulty([obj]) == pytest.approx(compute_difficulty(obj, answer_obj_count=1))

    def test_multiple_objects_simple_average(self) -> None:
        """설계안 §2: (1/|hidden|) · Σ D(obj) — 단순 평균."""
        objs = [
            {"sigma_threshold": 4.0, "hop": 1, "diameter": 3.0, "degree_norm": 0.2},
            {"sigma_threshold": 2.0, "hop": 3, "diameter": 3.0, "degree_norm": 0.7},
        ]
        expected = sum(compute_difficulty(o, answer_obj_count=2) for o in objs) / 2
        assert compute_scene_difficulty(objs, answer_obj_count=2) == pytest.approx(expected)

    def test_answer_obj_count_propagated(self) -> None:
        """answer_obj_count 가 compute_difficulty 로 전달되어야 한다."""
        obj = {"similar_count": 2.0}
        # answer_obj_count=3 → norm=2/2=1.0
        # answer_obj_count=5 → norm=2/4=0.5
        s3 = compute_scene_difficulty([obj], answer_obj_count=3)
        s5 = compute_scene_difficulty([obj], answer_obj_count=5)
        assert s3 > s5


# ---------------------------------------------------------------------------
# integrate_verification_v2  (answer_obj_count 파라미터 반영)
# ---------------------------------------------------------------------------


class TestIntegrateVerificationV2:
    def test_returns_three_floats(self) -> None:
        result = integrate_verification_v2({})
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)

    def test_scores_are_nonnegative(self) -> None:
        perception, logical, total = integrate_verification_v2({})
        assert perception >= 0.0
        assert logical >= 0.0
        assert total >= 0.0

    def test_hard_scene_higher_than_easy(self) -> None:
        hard = {"sigma_threshold": 1.0, "drr_slope": 1.0, "hop": 4, "diameter": 4.0, "degree_norm": 1.0}
        easy = {"sigma_threshold": 16.0, "drr_slope": 0.0, "hop": 0, "diameter": 1.0, "degree_norm": 0.0}
        _, _, total_hard = integrate_verification_v2(hard)
        _, _, total_easy = integrate_verification_v2(easy)
        assert total_hard > total_easy

    def test_similar_count_norm_uses_answer_obj_count(self) -> None:
        """similar_count / (answer_obj_count - 1)."""
        m = {"similar_count": 2.0}
        p4, _, _ = integrate_verification_v2(m, answer_obj_count=3)   # norm=2/2=1.0
        p7, _, _ = integrate_verification_v2(m, answer_obj_count=5)   # norm=2/4=0.5
        assert p4 > p7

    def test_weighted_sum_formula(self) -> None:
        metrics = {"sigma_threshold": 4.0, "drr_slope": 0.10, "hop": 2, "diameter": 4.0, "degree_norm": 0.5}
        w = ScoringWeights()
        perception, logical, total = integrate_verification_v2(metrics)
        expected_total = perception * w.total_perception + logical * w.total_logical
        assert total == pytest.approx(expected_total, rel=1e-6)
