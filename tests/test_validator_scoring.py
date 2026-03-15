from __future__ import annotations

import pytest

from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_difficulty,
    compute_scene_difficulty,
    integrate_verification,
    integrate_verification_v2,
    resolve_answer,
)
from discoverex.domain.verification import VerificationResult

# ---------------------------------------------------------------------------
# resolve_answer  (8조건, is_hidden_min_conditions=2 기본값)
# ---------------------------------------------------------------------------


class TestResolveAnswer:
    def test_two_conditions_returns_true(self) -> None:
        # drr_slope > 0.1 ✓, color_contrast <= 30 ✓ → 2개 충족
        metrics = {"drr_slope": 0.15, "color_contrast": 20.0}
        assert resolve_answer(metrics) is True

    def test_one_condition_returns_false(self) -> None:
        # drr_slope > 0.1 ✓, 나머지 기본값 → 1개만 충족
        metrics = {"drr_slope": 0.15}
        assert resolve_answer(metrics) is False

    def test_all_nine_conditions_met(self) -> None:
        metrics = {
            "drr_slope": 0.2,
            "similar_count": 2,
            "similar_distance": 50.0,
            "color_contrast": 15.0,
            "edge_strength": 300.0,
            "visual_degree": 3,
            "cluster_density": 3,
            "z_depth_hop": 2,
            "logical_degree": 4,
        }
        assert resolve_answer(metrics) is True

    def test_missing_keys_use_defaults_return_false(self) -> None:
        # 빈 dict: 모든 조건 기본값 → min 2개 미충족
        assert resolve_answer({}) is False

    def test_boundary_color_contrast_exactly_30(self) -> None:
        # color_contrast == 30 → <= 30 ✓ + drr_slope ✓ → True
        metrics = {"color_contrast": 30.0, "drr_slope": 0.15}
        assert resolve_answer(metrics) is True

    def test_boundary_color_contrast_above_30(self) -> None:
        # color_contrast > 30 → ❌ → drr_slope만 충족 → False
        metrics = {"color_contrast": 30.01, "drr_slope": 0.15}
        assert resolve_answer(metrics) is False

    def test_boundary_edge_strength_exactly_400(self) -> None:
        # edge_strength == 400 → <= 400 ✓ + drr_slope ✓ → True
        metrics = {"edge_strength": 400.0, "drr_slope": 0.15}
        assert resolve_answer(metrics) is True

    def test_drr_slope_condition(self) -> None:
        # drr_slope > 0.1 ✓ + color_contrast ✓ → 2 → True
        metrics = {"drr_slope": 0.15, "color_contrast": 20.0}
        assert resolve_answer(metrics) is True

    def test_similar_count_condition(self) -> None:
        # similar_count >= 1 ✓ + drr_slope ✓ → 2 → True
        metrics = {"similar_count": 1, "drr_slope": 0.15}
        assert resolve_answer(metrics) is True

    def test_similar_distance_condition(self) -> None:
        # similar_distance < 80 ✓ + drr_slope ✓ → 2 → True
        metrics = {"similar_distance": 60.0, "drr_slope": 0.15}
        assert resolve_answer(metrics) is True

    def test_visual_degree_condition(self) -> None:
        # visual_degree >= 2 ✓ + drr_slope ✓ → 2 → True
        metrics = {"visual_degree": 2, "drr_slope": 0.15}
        assert resolve_answer(metrics) is True

    def test_cluster_density_condition(self) -> None:
        # cluster_density >= 2 ✓ + drr_slope ✓ → 2 → True
        metrics = {"cluster_density": 2, "drr_slope": 0.15}
        assert resolve_answer(metrics) is True

    def test_min_conditions_override(self) -> None:
        # 3개 조건 충족, min_conditions=4 → False
        metrics = {"drr_slope": 0.15, "color_contrast": 20.0, "z_depth_hop": 2}
        assert resolve_answer(metrics, min_conditions=4) is False

    def test_min_conditions_1_easy_pass(self) -> None:
        # min_conditions=1 → drr_slope 하나만으로 True
        metrics = {"drr_slope": 0.15}
        assert resolve_answer(metrics, min_conditions=1) is True


# ---------------------------------------------------------------------------
# compute_difficulty  (9항 수식)
# ---------------------------------------------------------------------------


class TestComputeDifficulty:
    def test_zero_metrics_returns_nonnegative(self) -> None:
        # 모든 항이 기본값 → 0 이상
        score = compute_difficulty({})
        assert score >= 0.0

    def test_high_difficulty_metrics_exceeds_low(self) -> None:
        easy = {
            "degree_norm": 0.0,
            "cluster_density": 0,
            "hop": 0,
            "diameter": 4.0,
            "drr_slope": 0.0,
            "sigma_threshold": 16.0,
            "similar_count": 0,
            "similar_distance": 100.0,
            "color_contrast": 100.0,
            "edge_strength": 100.0,
        }
        hard = {
            "degree_norm": 0.9,
            "cluster_density": 8,
            "hop": 3,
            "diameter": 4.0,
            "drr_slope": 0.25,
            "sigma_threshold": 1.0,
            "similar_count": 4,
            "similar_distance": 10.0,
            "color_contrast": 0.0,
            "edge_strength": 0.0,
        }
        assert compute_difficulty(hard) > compute_difficulty(easy)

    def test_missing_keys_use_defaults(self) -> None:
        score = compute_difficulty({})
        assert score >= 0.0

    def test_sigma_zero_guarded(self) -> None:
        metrics = {"sigma_threshold": 0.0}
        score = compute_difficulty(metrics)
        assert score >= 0.0

    def test_diameter_zero_guarded(self) -> None:
        metrics = {"hop": 2, "diameter": 0.0}
        score = compute_difficulty(metrics)
        assert score >= 0.0

    def test_similar_distance_zero_guarded(self) -> None:
        # 1/(1+0) = 1.0 — 분모가 1 이므로 ZeroDivisionError 없어야 함
        metrics = {"similar_distance": 0.0}
        score = compute_difficulty(metrics)
        assert score >= 0.0

    def test_all_nine_terms_contribute(self) -> None:
        base = compute_difficulty({})
        # degree_norm=1 → degree 항 추가
        assert compute_difficulty({"degree_norm": 1.0}) > base - 1e-9


# ---------------------------------------------------------------------------
# compute_scene_difficulty  (object_count 가중 평균)
# ---------------------------------------------------------------------------


class TestComputeSceneDifficulty:
    def test_empty_list_returns_zero(self) -> None:
        assert compute_scene_difficulty([]) == 0.0

    def test_single_object_equals_compute_difficulty(self) -> None:
        obj = {
            "sigma_threshold": 4.0,
            "hop": 2,
            "diameter": 4.0,
            "degree_norm": 0.3,
            "drr_slope": 0.12,
        }
        assert compute_scene_difficulty([obj]) == pytest.approx(compute_difficulty(obj))

    def test_multiple_objects_equal_count_is_average(self) -> None:
        """object_count_map 없거나 count=1 이면 단순 평균."""
        objs = [
            {
                "sigma_threshold": 4.0,
                "hop": 1,
                "diameter": 3.0,
                "degree_norm": 0.2,
                "drr_slope": 0.08,
            },
            {
                "sigma_threshold": 2.0,
                "hop": 3,
                "diameter": 3.0,
                "degree_norm": 0.7,
                "drr_slope": 0.20,
            },
        ]
        expected = sum(compute_difficulty(o) for o in objs) / 2
        assert compute_scene_difficulty(objs) == pytest.approx(expected)

    def test_object_count_weighted_average(self) -> None:
        """object_count_map 가중치가 반영되어야 한다."""
        obj_a = {"obj_id": "a", "sigma_threshold": 2.0, "degree_norm": 0.8}
        obj_b = {"obj_id": "b", "sigma_threshold": 8.0, "degree_norm": 0.1}
        ocount = {"a": 3, "b": 1}
        expected = (3 * compute_difficulty(obj_a) + 1 * compute_difficulty(obj_b)) / 4
        result = compute_scene_difficulty([obj_a, obj_b], object_count_map=ocount)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_missing_obj_id_defaults_count_to_1(self) -> None:
        """obj_id 없는 경우 count=1 로 처리."""
        obj = {"sigma_threshold": 4.0}
        ocount = {"irrelevant_id": 5}
        assert compute_scene_difficulty(
            [obj], object_count_map=ocount
        ) == pytest.approx(compute_difficulty(obj))


class TestIntegrateVerification:
    def test_always_passes_while_preserving_total_score(self) -> None:
        logical = VerificationResult(score=1.0, pass_=True, signals={})
        perception = VerificationResult(score=0.2, pass_=False, signals={})

        final = integrate_verification(logical, perception, pass_threshold=0.9)

        assert final.total_score == pytest.approx(0.6)
        assert final.pass_ is True
        assert final.failure_reason == ""


# ---------------------------------------------------------------------------
# integrate_verification_v2
# ---------------------------------------------------------------------------


class TestIntegrateVerificationV2:
    def test_returns_three_floats(self) -> None:
        result = integrate_verification_v2({})
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)

    def test_high_difficulty_passes_threshold(self) -> None:
        hard = {
            "sigma_threshold": 1.0,
            "drr_slope": 1.0,
            "hop": 4,
            "diameter": 4.0,
            "degree_norm": 1.0,
        }
        perception, logical, total = integrate_verification_v2(
            hard, pass_threshold=0.35
        )
        assert total >= 0.35

    def test_easy_scene_below_threshold(self) -> None:
        easy = {
            "sigma_threshold": 16.0,
            "drr_slope": 0.0,
            "hop": 0,
            "diameter": 1.0,
            "degree_norm": 0.0,
        }
        _, _, total = integrate_verification_v2(easy, pass_threshold=0.35)
        assert total < 0.35

    def test_scores_are_nonnegative(self) -> None:
        perception, logical, total = integrate_verification_v2({})
        assert perception >= 0.0
        assert logical >= 0.0
        assert total >= 0.0

    def test_weighted_sum_formula(self) -> None:
        metrics = {
            "sigma_threshold": 4.0,
            "drr_slope": 0.10,
            "hop": 2,
            "diameter": 4.0,
            "degree_norm": 0.5,
        }
        w = ScoringWeights()
        perception, logical, total = integrate_verification_v2(metrics)
        expected_total = perception * w.total_perception + logical * w.total_logical
        assert total == pytest.approx(expected_total, rel=1e-6)
