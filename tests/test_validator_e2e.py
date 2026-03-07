"""
Validator 파이프라인 End-to-End 테스트

테스트 전략
-----------
* Phase 1 (MobileSAM) / Phase 2 (Moondream2) / Phase 3 (YOLO+CLIP) 는
  실제 모델 가중치와 GPU 없이 실행 불가 → Dummy 어댑터 사용
* Dummy 어댑터가 반환하는 고정값을 직접 추적해 Phase 4 수치를 사전 계산하고,
  실제 실행 결과와 비교한다 (단순 타입 검사가 아닌 수치 검증).

Dummy 어댑터 고정 출력값
--------------------------
  DummyPhysical  : occlusion=0.45, z_depth_hop=2, cluster_density=3
  DummyLogical   : degree=3, hop=2, diameter=4.0
  DummyVisual    : sigma=4.0, drr=0.55  (obj_0, obj_1 고정)

Phase 4 수식 (ScoringWeights 기본값 기준 — 정규화 적용):
  p_denom    = 0.50+0.50 = 1.0
  perception = (0.50*(1/4) + 0.50*0.45) / 1.0 = 0.35
  l_denom    = 0.55+0.45 = 1.0
  logical    = (0.55*0.5 + 0.45*1.0) / 1.0 = 0.725
  total      = 0.35*0.45 + 0.725*0.55 = 0.55625  → PASS
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from discoverex.adapters.outbound.models.dummy import (
    DummyLogicalExtraction,
    DummyPhysicalExtraction,
    DummyVisualVerification,
)
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_difficulty,
    compute_scene_difficulty,
    integrate_verification_v2,
    resolve_answer,
)
from discoverex.domain.verification import VerificationBundle
from discoverex.models.types import (
    LogicalStructure,
    ModelHandle,
    PhysicalMetadata,
    VisualVerification,
)

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_handle(name: str) -> ModelHandle:
    return ModelHandle(name=name, version="dummy", runtime="dummy")


def _make_png(path: Path, width: int = 64, height: int = 64) -> None:
    try:
        from PIL import Image

        img = Image.new("RGBA", (width, height), color=(128, 128, 128, 255))
        img.save(path, format="PNG")
    except ModuleNotFoundError:
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00@\x00\x00\x00@\x08\x02\x00\x00\x00"
            b"\x25\x3e\x45\x56"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def _make_orchestrator(
    physical_port: Any = None,
    logical_port: Any = None,
    visual_port: Any = None,
    pass_threshold: float = 0.35,
    scoring_weights: ScoringWeights | None = None,
) -> ValidatorOrchestrator:
    return ValidatorOrchestrator(
        physical_port=physical_port or DummyPhysicalExtraction(),
        logical_port=logical_port or DummyLogicalExtraction(),
        visual_port=visual_port or DummyVisualVerification(),
        physical_handle=_make_handle("physical"),
        logical_handle=_make_handle("logical"),
        visual_handle=_make_handle("visual"),
        pass_threshold=pass_threshold,
        scoring_weights=scoring_weights,
    )


# ---------------------------------------------------------------------------
# 커스텀 어댑터 — "어려운" 시나리오 (max 점수 유도)
# ---------------------------------------------------------------------------


class _HardVisualVerification:
    """sigma=1.0, drr=0.0 → perception 최댓값."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def verify(
        self, composite_image: Path, sigma_levels: list[float]
    ) -> VisualVerification:  # noqa: ARG002
        return VisualVerification(
            sigma_threshold_map={"obj_0": 1.0, "obj_1": 1.0},
            detail_retention_rate_map={"obj_0": 0.0, "obj_1": 0.0},
        )

    def unload(self) -> None:
        pass


class _HardLogicalExtraction:
    """hop = diameter = 4, degree = 4 → logical 최댓값."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def extract(
        self, composite_image: Path, physical: PhysicalMetadata
    ) -> LogicalStructure:  # noqa: ARG002
        obj_ids = list(physical.occlusion_map.keys()) or ["obj_0", "obj_1"]
        return LogicalStructure(
            relations=[],
            degree_map={oid: 4 for oid in obj_ids},
            hop_map={oid: 4 for oid in obj_ids},
            diameter=4.0,
        )

    def unload(self) -> None:
        pass


# ---------------------------------------------------------------------------
# 사전 계산된 예상값 (ScoringWeights 기본값 / 정규화 수식 기준)
# ---------------------------------------------------------------------------

_W = ScoringWeights()
_P_DENOM = _W.perception_sigma + _W.perception_drr  # 1.0
_L_DENOM = _W.logical_hop + _W.logical_degree  # 1.0

# 표준 (dummy) 시나리오
_PERC_STD = (
    _W.perception_sigma * (1.0 / 4.0) + _W.perception_drr * (1.0 - 0.55)
) / _P_DENOM  # 0.35
_LOGI_STD = (
    _W.logical_hop * (2.0 / 4.0) + _W.logical_degree * 1.0**2
) / _L_DENOM  # 0.725
_TOT_STD = _PERC_STD * _W.total_perception + _LOGI_STD * _W.total_logical  # 0.55625

# 어려운 시나리오 (sigma=1, drr=0, hop=diameter=4, degree=4)
_PERC_HARD = (_W.perception_sigma * 1.0 + _W.perception_drr * 1.0) / _P_DENOM  # 1.0
_LOGI_HARD = (_W.logical_hop * 1.0 + _W.logical_degree * 1.0) / _L_DENOM  # 1.0
_TOT_HARD = _PERC_HARD * _W.total_perception + _LOGI_HARD * _W.total_logical  # 1.0


# ===========================================================================
# 1. 전체 파이프라인 E2E — Dummy 어댑터
# ===========================================================================


class TestE2EFullPipelineDummy:
    @pytest.fixture()
    def orch(self) -> ValidatorOrchestrator:
        return _make_orchestrator()

    @pytest.fixture()
    def composite(self, tmp_path: Path) -> Path:
        p = tmp_path / "composite.png"
        _make_png(p)
        return p

    def test_returns_verification_bundle(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        assert isinstance(
            orch.run(composite_image=composite, object_layers=layers),
            VerificationBundle,
        )

    def test_two_layers_perception_score(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.perception.score == pytest.approx(_PERC_STD, rel=1e-4)

    def test_two_layers_logical_score(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.logical.score == pytest.approx(_LOGI_STD, rel=1e-4)

    def test_two_layers_total_score(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.final.total_score == pytest.approx(_TOT_STD, rel=1e-4)

    def test_two_layers_passes_threshold(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.final.pass_ is True
        assert bundle.final.failure_reason == ""

    def test_two_layers_answer_obj_count(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.logical.signals["answer_obj_count"] == 2

    def test_two_layers_scene_difficulty_signal(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        expected_d = compute_difficulty(
            {
                "occlusion_ratio": 0.45,
                "sigma_threshold": 4.0,
                "hop": 2,
                "diameter": 4.0,
                "degree_norm": 1.0,
                "detail_retention_rate": 0.55,
            }
        )
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.logical.signals["scene_difficulty"] == pytest.approx(
            expected_d, rel=1e-4
        )

    def test_required_signal_keys_present(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        for key in ("sigma_threshold_map", "detail_retention_rate_map"):
            assert key in bundle.perception.signals
        for key in (
            "answer_obj_count",
            "scene_difficulty",
            "degree_map",
            "hop_map",
            "diameter",
        ):
            assert key in bundle.logical.signals

    def test_one_layer_total_score(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        """
        1개 레이어: obj_1 은 physical/logical 기본값(0) 사용.
        obj_1.logical = 0.0  (hop=0, degree_norm=0)
        avg_perception = 0.35, avg_logical = 0.725/2 = 0.3625
        total = 0.35*0.45 + 0.3625*0.55 = 0.356875
        """
        layer = tmp_path / "obj_0.png"
        _make_png(layer)
        avg_perc = (_PERC_STD + _PERC_STD) / 2  # obj_1도 sigma/drr는 visual에서
        avg_logi = (_LOGI_STD + 0.0) / 2
        expected_tot = avg_perc * _W.total_perception + avg_logi * _W.total_logical

        bundle = orch.run(composite_image=composite, object_layers=[layer])
        assert bundle.final.total_score == pytest.approx(expected_tot, rel=1e-4)

    def test_one_layer_answer_obj_count(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layer = tmp_path / "obj_0.png"
        _make_png(layer)
        bundle = orch.run(composite_image=composite, object_layers=[layer])
        assert bundle.logical.signals["answer_obj_count"] == 1

    def test_no_layers_uses_default_objs(
        self, orch: ValidatorOrchestrator, composite: Path
    ) -> None:
        bundle = orch.run(composite_image=composite, object_layers=[])
        assert bundle.final.total_score == pytest.approx(_TOT_STD, rel=1e-4)
        assert bundle.final.pass_ is True

    def test_pass_field_is_bool(
        self, orch: ValidatorOrchestrator, composite: Path
    ) -> None:
        assert isinstance(
            orch.run(composite_image=composite, object_layers=[]).final.pass_, bool
        )

    def test_total_score_within_unit_range(
        self, orch: ValidatorOrchestrator, composite: Path
    ) -> None:
        bundle = orch.run(composite_image=composite, object_layers=[])
        assert 0.0 <= bundle.final.total_score <= 1.0

    def test_custom_weights_change_score(self, composite: Path, tmp_path: Path) -> None:
        """ScoringWeights 를 바꾸면 점수가 달라짐을 검증."""
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        default_orch = _make_orchestrator()
        biased_orch = _make_orchestrator(
            scoring_weights=ScoringWeights(
                perception_sigma=0.90,
                perception_drr=0.10,
                logical_hop=0.50,
                logical_degree=0.50,
                total_perception=0.45,
                total_logical=0.55,
            )
        )
        s1 = default_orch.run(
            composite_image=composite, object_layers=layers
        ).final.total_score
        s2 = biased_orch.run(
            composite_image=composite, object_layers=layers
        ).final.total_score
        assert s1 != pytest.approx(s2, rel=1e-3)


# ===========================================================================
# 2. "어려운" 시나리오 — max 점수 (= 1.0)
# ===========================================================================


class TestE2EHardScenarioPass:
    @pytest.fixture()
    def orch(self) -> ValidatorOrchestrator:
        return _make_orchestrator(
            logical_port=_HardLogicalExtraction(),
            visual_port=_HardVisualVerification(),
        )

    @pytest.fixture()
    def composite(self, tmp_path: Path) -> Path:
        p = tmp_path / "composite.png"
        _make_png(p)
        return p

    def test_hard_scenario_max_total_score(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        assert orch.run(
            composite_image=composite, object_layers=layers
        ).final.total_score == pytest.approx(_TOT_HARD, rel=1e-4)

    def test_hard_scenario_passes(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.final.pass_ is True and bundle.final.failure_reason == ""

    def test_hard_scenario_perception_and_logical(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.perception.score == pytest.approx(_PERC_HARD, rel=1e-4)
        assert bundle.logical.score == pytest.approx(_LOGI_HARD, rel=1e-4)


# ===========================================================================
# 3. Phase 4 단독 E2E — resolve → score → difficulty 체인
# ===========================================================================


class TestE2EPhase4Chain:
    def test_resolve_and_score_standard_metrics(self) -> None:
        metrics = {
            "occlusion_ratio": 0.45,
            "sigma_threshold": 4.0,
            "degree": 3,
            "degree_norm": 1.0,
            "z_depth_hop": 2,
            "neighbor_count": 3,
            "hop": 2,
            "diameter": 4.0,
            "detail_retention_rate": 0.55,
        }
        assert resolve_answer(metrics) is True
        perc, logi, total = integrate_verification_v2(metrics)
        assert perc == pytest.approx(_PERC_STD, rel=1e-4)
        assert logi == pytest.approx(_LOGI_STD, rel=1e-4)
        assert total == pytest.approx(_TOT_STD, rel=1e-4)

    def test_resolve_fails_below_two_conditions(self) -> None:
        assert (
            resolve_answer(
                {
                    "occlusion_ratio": 0.1,
                    "sigma_threshold": 8.0,
                    "degree": 0,
                    "z_depth_hop": 0,
                    "neighbor_count": 0,
                }
            )
            is False
        )

    def test_difficulty_and_scene_difficulty_chain(self) -> None:
        obj = {
            "occlusion_ratio": 0.45,
            "sigma_threshold": 4.0,
            "hop": 2,
            "diameter": 4.0,
            "degree_norm": 1.0,
            "detail_retention_rate": 0.55,
        }
        d = compute_difficulty(obj)
        assert d > 0.0
        assert compute_scene_difficulty([obj, obj]) == pytest.approx(d, rel=1e-4)

    def test_hard_metrics_full_chain(self) -> None:
        hard = {
            "occlusion_ratio": 0.5,
            "sigma_threshold": 1.0,
            "degree": 4,
            "degree_norm": 1.0,
            "z_depth_hop": 3,
            "neighbor_count": 4,
            "hop": 4,
            "diameter": 4.0,
            "detail_retention_rate": 0.0,
        }
        assert resolve_answer(hard) is True
        _, _, total = integrate_verification_v2(hard)
        assert total == pytest.approx(_TOT_HARD, rel=1e-4)
        assert total >= 0.35

    def test_easy_metrics_full_chain(self) -> None:
        easy = {
            "occlusion_ratio": 0.0,
            "sigma_threshold": 16.0,
            "degree": 0,
            "degree_norm": 0.0,
            "z_depth_hop": 0,
            "neighbor_count": 0,
            "hop": 0,
            "diameter": 1.0,
            "detail_retention_rate": 0.99,
        }
        assert resolve_answer(easy) is False
        _, _, total = integrate_verification_v2(easy)
        assert total < 0.10

    def test_total_score_is_weighted_sum_of_sub_scores(self) -> None:
        metrics = {
            "sigma_threshold": 2.0,
            "detail_retention_rate": 0.4,
            "hop": 3,
            "diameter": 4.0,
            "degree_norm": 0.6,
        }
        w = ScoringWeights()
        perc, logi, total = integrate_verification_v2(metrics)
        assert total == pytest.approx(
            perc * w.total_perception + logi * w.total_logical, rel=1e-6
        )

    def test_all_scores_nonnegative_on_empty_metrics(self) -> None:
        perc, logi, total = integrate_verification_v2({})
        assert perc >= 0.0 and logi >= 0.0 and total >= 0.0

    def test_custom_weights_alter_score(self) -> None:
        metrics = {
            "sigma_threshold": 4.0,
            "detail_retention_rate": 0.55,
            "hop": 2,
            "diameter": 4.0,
            "degree_norm": 1.0,
        }
        _, _, total_default = integrate_verification_v2(metrics)
        w_custom = ScoringWeights(
            perception_sigma=0.90,
            perception_drr=0.10,
            logical_hop=0.90,
            logical_degree=0.10,
        )
        _, _, total_custom = integrate_verification_v2(metrics, weights=w_custom)
        assert total_default != pytest.approx(total_custom, rel=1e-3)


# ===========================================================================
# 4. 실제 모델 어댑터 스텁 (skip)
# ===========================================================================


@pytest.mark.skip(reason="MobileSAM: timm 패키지 미설치")
def test_phase1_real_mobilesam_loads() -> None:
    from discoverex.adapters.outbound.models.hf_mobilesam import (
        MobileSAMAdapter,  # noqa: F401
    )

    raise AssertionError("이 테스트는 skip 되어야 함")


@pytest.mark.skip(reason="Moondream2: transformers 미설치")
def test_phase2_real_moondream2_loads() -> None:
    from discoverex.adapters.outbound.models.hf_moondream2 import (
        Moondream2Adapter,  # noqa: F401
    )

    raise AssertionError("이 테스트는 skip 되어야 함")


@pytest.mark.skip(reason="YOLO+CLIP: transformers 미설치")
def test_phase3_real_yolo_clip_loads() -> None:
    from discoverex.adapters.outbound.models.hf_yolo_clip import (
        YoloCLIPAdapter,  # noqa: F401
    )

    raise AssertionError("이 테스트는 skip 되어야 함")
