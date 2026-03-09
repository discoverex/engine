from __future__ import annotations

import pytest

from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_difficulty,
    compute_scene_difficulty,
    integrate_verification_v2,
    resolve_answer,
)

# ---------------------------------------------------------------------------
# resolve_answer
# ---------------------------------------------------------------------------


class TestResolveAnswer:
    def test_two_conditions_returns_true(self) -> None:
        metrics = {
            "occlusion_ratio": 0.5,  # > 0.3 ✓
            "sigma_threshold": 2.0,  # <= 4 ✓
            "degree": 0,
            "z_depth_hop": 0,
            "neighbor_count": 0,
        }
        assert resolve_answer(metrics) is True

    def test_one_condition_returns_false(self) -> None:
        metrics = {
            "occlusion_ratio": 0.5,  # > 0.3 ✓
            "sigma_threshold": 16.0,  # not <= 4
            "degree": 0,
            "z_depth_hop": 0,
            "neighbor_count": 0,
        }
        assert resolve_answer(metrics) is False

    def test_all_conditions_met(self) -> None:
        metrics = {
            "occlusion_ratio": 0.6,
            "sigma_threshold": 2.0,
            "degree": 5,
            "z_depth_hop": 3,
            "neighbor_count": 4,
        }
        assert resolve_answer(metrics) is True

    def test_missing_keys_use_defaults(self) -> None:
        # Empty dict: all conditions False → should return False
        assert resolve_answer({}) is False

    def test_boundary_occlusion_exactly_03(self) -> None:
        # occlusion_ratio == 0.3 is NOT > 0.3
        metrics = {"occlusion_ratio": 0.3, "sigma_threshold": 2.0}
        assert resolve_answer(metrics) is False

    def test_boundary_sigma_exactly_4(self) -> None:
        # sigma_threshold == 4 IS <= 4
        metrics = {"occlusion_ratio": 0.5, "sigma_threshold": 4.0}
        assert resolve_answer(metrics) is True


# ---------------------------------------------------------------------------
# compute_difficulty
# ---------------------------------------------------------------------------


class TestComputeDifficulty:
    def test_zero_metrics_returns_nonnegative(self) -> None:
        metrics = {
            "occlusion_ratio": 0.0,
            "sigma_threshold": 1.0,
            "hop": 0,
            "diameter": 1.0,
            "degree_norm": 0.0,
            "drr_slope": 0.0,
        }
        score = compute_difficulty(metrics)
        assert score >= 0.0

    def test_high_difficulty_metrics_exceeds_low(self) -> None:
        easy = {
            "occlusion_ratio": 0.0,
            "sigma_threshold": 16.0,
            "hop": 0,
            "diameter": 4.0,
            "degree_norm": 0.0,
            "drr_slope": 0.0,   # 소실 속도 낮음 = 쉬움
        }
        hard = {
            "occlusion_ratio": 0.9,
            "sigma_threshold": 1.0,
            "hop": 3,
            "diameter": 4.0,
            "degree_norm": 0.9,
            "drr_slope": 0.25,  # 소실 속도 높음 = 어려움
        }
        assert compute_difficulty(hard) > compute_difficulty(easy)

    def test_missing_keys_use_defaults(self) -> None:
        score = compute_difficulty({})
        assert score >= 0.0

    def test_sigma_zero_guarded(self) -> None:
        # sigma_threshold=0 must not raise ZeroDivisionError
        metrics = {"sigma_threshold": 0.0}
        score = compute_difficulty(metrics)
        assert score >= 0.0

    def test_diameter_zero_guarded(self) -> None:
        metrics = {"hop": 2, "diameter": 0.0}
        score = compute_difficulty(metrics)
        assert score >= 0.0


# ---------------------------------------------------------------------------
# compute_scene_difficulty
# ---------------------------------------------------------------------------


class TestComputeSceneDifficulty:
    def test_empty_list_returns_zero(self) -> None:
        assert compute_scene_difficulty([]) == 0.0

    def test_single_object_equals_compute_difficulty(self) -> None:
        obj = {
            "occlusion_ratio": 0.5,
            "sigma_threshold": 4.0,
            "hop": 2,
            "diameter": 4.0,
            "degree_norm": 0.3,
            "drr_slope": 0.12,
        }
        assert compute_scene_difficulty([obj]) == pytest.approx(compute_difficulty(obj))

    def test_multiple_objects_is_average(self) -> None:
        objs = [
            {
                "occlusion_ratio": 0.4,
                "sigma_threshold": 4.0,
                "hop": 1,
                "diameter": 3.0,
                "degree_norm": 0.2,
                "drr_slope": 0.08,
            },
            {
                "occlusion_ratio": 0.8,
                "sigma_threshold": 2.0,
                "hop": 3,
                "diameter": 3.0,
                "degree_norm": 0.7,
                "drr_slope": 0.20,
            },
        ]
        expected = sum(compute_difficulty(o) for o in objs) / 2
        assert compute_scene_difficulty(objs) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# integrate_verification_v2
# ---------------------------------------------------------------------------


class TestIntegrateVerificationV2:
    def test_returns_three_floats(self) -> None:
        result = integrate_verification_v2({})
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)

    def test_high_difficulty_passes_threshold(self) -> None:
        # 정규화 수식 기준 (drr_slope 방식):
        # perception = (0.5*(1/1) + 0.5*1.0) / 1.0 = 1.0  (sigma=1, drr_slope=1.0)
        # logical    = (0.55*(4/4) + 0.45*(1.0)²) / 1.0 = 1.0
        # total      = 1.0*0.45 + 1.0*0.55 = 1.0 >= 0.35
        hard = {
            "sigma_threshold": 1.0,
            "drr_slope": 1.0,   # 빠른 소실 = 어려움 (직접 기여)
            "hop": 4,
            "diameter": 4.0,
            "degree_norm": 1.0,
        }
        perception, logical, total = integrate_verification_v2(
            hard, pass_threshold=0.35
        )
        assert total >= 0.35

    def test_easy_scene_below_threshold(self) -> None:
        # sigma=16 → 1/16 = 0.0625, drr_slope=0.0 → perception 낮음
        # hop=0, degree_norm=0 → logical=0
        easy = {
            "sigma_threshold": 16.0,
            "drr_slope": 0.0,   # 소실 없음 = 쉬움
            "hop": 0,
            "diameter": 1.0,
            "degree_norm": 0.0,
        }
        _, _, total = integrate_verification_v2(easy, pass_threshold=0.35)
        assert total < 0.35

    def test_scores_are_nonnegative(self) -> None:
        for _ in range(5):
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
