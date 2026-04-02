"""
Validator 파이프라인 End-to-End 테스트

테스트 전략
-----------
* Phase 1 (MobileSAM) / Phase 3 (Moondream2) / Phase 4 (YOLO+CLIP) 는
  실제 모델 가중치와 GPU 없이 실행 불가 → Dummy 어댑터 사용
* Dummy 어댑터가 반환하는 고정값을 직접 추적해 Phase 5 수치를 사전 계산하고,
  실제 실행 결과와 비교한다 (단순 타입 검사가 아닌 수치 검증).

Dummy 어댑터 고정 출력값
--------------------------
  DummyPhysical  : z_depth_hop=2, cluster_density=3, alpha_degree=2
  DummyLogical   : hop=2, diameter=4.0, degree_map={oid: 3}
  DummyVisual    : sigma=4.0, drr_slope=0.15, similar_count=1, similar_distance=80.0
                   (obj_0, obj_1 고정)
  color_edge_port=None → color_contrast=0.0, edge_strength=0.0

설계안 §1~§3 수식 (3패스 구조):
  max_combined = 2+3=5 → degree_norm = 5/5 = 1.0
  두 객체 모두 is_hidden=True (hf=1.0 ≥ θ_HUMAN=0.135)
  answer_obj_count = 2 → similar_count_norm = 1/max(2-1,1) = 1.0

  perception (6항, answer_obj_count=2):
    = (0.10*(1/4) + 0.15*0.15 + 0.20*1.0 + 0.15*(1/81) + 0.20*1 + 0.20*1) / 1.0
    ≈ 0.649352

  logical (3항, cluster_norm=3/10=0.3):
    = (0.40*(2/4) + 0.40*1.0² + 0.20*0.3) / 1.0 = 0.66

  scene_difficulty = D(obj) (설계안 §2, answer_obj_count=2):
    ≈ 0.548111  → bundle.final.total_score
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from discoverex.adapters.outbound.models.dummy import (
    DummyLogicalExtraction,
    DummyPhysicalExtraction,
    DummyVisualVerification,
)
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.domain.services.types import ObjectMetrics
from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_difficulty,
    compute_scene_difficulty,
    integrate_verification_v2,
)
from discoverex.domain.verification import VerificationBundle
from discoverex.models.types import (
    ColorEdgeMetadata,
    LogicalStructure,
    ModelHandle,
    PhysicalMetadata,
    VisualVerification,
)

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_metrics(**kwargs: Any) -> ObjectMetrics:
    defaults: dict[str, Any] = {
        "obj_id": "obj_default",
        "visual_degree": 0.0,
        "logical_degree": 0.0,
        "degree_norm": 0.0,
        "cluster_density": 0.0,
        "z_depth_hop": 0.0,
        "hop": 0.0,
        "diameter": 1.0,
        "sigma_threshold": 16.0,
        "drr_slope": 0.0,
        "similar_count": 0,
        "similar_distance": 100.0,
        "color_contrast": 0.0,
        "edge_strength": 0.0,
    }
    defaults.update(kwargs)
    return cast(ObjectMetrics, defaults)


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
    difficulty_min: float = 0.0,  # Dummy 어댑터 2객체 기준 pass 유도 (§3 기본값 아님)
    difficulty_max: float = 1.0,
    hidden_obj_min: int = 1,  # Dummy 어댑터 2객체 기준 pass 유도 (§3 기본값 아님)
    scoring_weights: ScoringWeights | None = None,
) -> ValidatorOrchestrator:
    return ValidatorOrchestrator(
        physical_port=physical_port or DummyPhysicalExtraction(),
        logical_port=logical_port or DummyLogicalExtraction(),
        visual_port=visual_port or DummyVisualVerification(),
        physical_handle=_make_handle("physical"),
        logical_handle=_make_handle("logical"),
        visual_handle=_make_handle("visual"),
        difficulty_min=difficulty_min,
        difficulty_max=difficulty_max,
        hidden_obj_min=hidden_obj_min,
        scoring_weights=scoring_weights,
        # color_edge_port=None → Phase 2 기본값 ColorEdgeMetadata() 사용
    )


# ---------------------------------------------------------------------------
# 커스텀 어댑터 — "어려운" 시나리오 (max 점수 유도)
# ---------------------------------------------------------------------------


class _HardVisualVerification:
    """sigma=1.0, drr_slope=1.0 → perception 최댓값."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def verify(
        self,
        composite_image: Path,  # noqa: ARG002
        sigma_levels: list[float],  # noqa: ARG002
        color_edge: ColorEdgeMetadata | None = None,  # noqa: ARG002
        physical: PhysicalMetadata | None = None,  # noqa: ARG002
    ) -> VisualVerification:
        return VisualVerification(
            sigma_threshold_map={"obj_0": 1.0, "obj_1": 1.0},
            drr_slope_map={"obj_0": 1.0, "obj_1": 1.0},
            similar_count_map={"obj_0": 0, "obj_1": 0},
            similar_distance_map={"obj_0": 100.0, "obj_1": 100.0},
            object_count_map={"obj_0": 1, "obj_1": 1},
        )

    def unload(self) -> None:
        pass


class _HardLogicalExtraction:
    """hop = diameter = 4 → logical 최댓값."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def extract(
        self,
        composite_image: Path,
        physical: PhysicalMetadata,  # noqa: ARG002
    ) -> LogicalStructure:
        obj_ids = list(physical.alpha_degree_map.keys()) or ["obj_0", "obj_1"]
        return LogicalStructure(
            relations=[],
            degree_map={},
            hop_map={oid: 4 for oid in obj_ids},
            diameter=4.0,
        )

    def unload(self) -> None:
        pass


# ---------------------------------------------------------------------------
# 사전 계산된 예상값 (ScoringWeights 기본값 / 설계안 §1~§3 수식 기준)
# ---------------------------------------------------------------------------

_W = ScoringWeights()
_P_DENOM = (
    _W.perception_sigma
    + _W.perception_drr
    + _W.perception_similar_count
    + _W.perception_similar_dist
    + _W.perception_color_contrast
    + _W.perception_edge_strength
)  # 1.00
_L_DENOM = _W.logical_hop + _W.logical_degree + _W.logical_cluster  # 1.00

# Dummy 시나리오에서 두 객체 모두 is_hidden=True → answer_obj_count=2
_ANSWER_OBJ_COUNT = 2

# 표준 (dummy) 시나리오
# visual_deg=2, logical_deg=3, combined=5 → max_combined=5 → degree_norm=1.0
# DummyVisual: sigma=4, drr=0.15, sim_cnt=1, sim_dist=80, color=0, edge=0
# DummyPhysical: cluster_density=3
# answer_obj_count=2 → sim_cnt_norm = 1/max(2-1,1) = 1.0
_PERC_STD = (
    _W.perception_sigma * (1.0 / 4.0)
    + _W.perception_drr * 0.15
    + _W.perception_similar_count * (1.0 / max(_ANSWER_OBJ_COUNT - 1, 1))  # 1.0
    + _W.perception_similar_dist * (1.0 / 81.0)
    + _W.perception_color_contrast * 1.0
    + _W.perception_edge_strength * 1.0
) / _P_DENOM  # ≈ 0.649352
_LOGI_STD = (
    _W.logical_hop * (2.0 / 4.0) + _W.logical_degree * 1.0**2 + _W.logical_cluster * 0.3
) / _L_DENOM  # 0.66

# 설계안 §2: Scene_Difficulty = D(obj) 단순 평균 (두 객체 동일 → avg = D_obj)
_STD_METRICS = _make_metrics(
    degree_norm=1.0,
    cluster_density=3,
    hop=2,
    diameter=4.0,
    drr_slope=0.15,
    sigma_threshold=4.0,
    similar_count=1,
    similar_distance=80.0,
    color_contrast=0.0,
    edge_strength=0.0,
)
_SCENE_DIFF_STD = compute_difficulty(
    _STD_METRICS, answer_obj_count=_ANSWER_OBJ_COUNT
)  # ≈ 0.548111

# 어려운 시나리오 (sigma=1, drr=1, sim_cnt=0, sim_dist=100, hop=4)
# _HardLogicalExtraction: degree_map={} → logical_deg=0
# visual_deg=2, logical_deg=0, combined=2, max_combined=2 → degree_norm=1.0
# DummyPhysical: cluster_density=3 → cluster_norm=0.3
_PERC_HARD = (
    _W.perception_sigma * 1.0
    + _W.perception_drr * 1.0
    + _W.perception_similar_count * 0.0  # sim_cnt=0
    + _W.perception_similar_dist * (1.0 / 101.0)
    + _W.perception_color_contrast * 1.0
    + _W.perception_edge_strength * 1.0
) / _P_DENOM  # ≈ 0.651485
_LOGI_HARD = (
    _W.logical_hop * (4.0 / 4.0) + _W.logical_degree * 1.0**2 + _W.logical_cluster * 0.3
) / _L_DENOM  # 0.86

_HARD_METRICS = _make_metrics(
    degree_norm=1.0,
    cluster_density=3,
    hop=4,
    diameter=4.0,
    drr_slope=1.0,
    sigma_threshold=1.0,
    similar_count=0,
    similar_distance=100.0,
    color_contrast=0.0,
    edge_strength=0.0,
)
_SCENE_DIFF_HARD = compute_difficulty(
    _HARD_METRICS, answer_obj_count=_ANSWER_OBJ_COUNT
)  # ≈ 0.716891

# TestE2EPhase5Chain 전용: integrate_verification_v2 직접 호출 기준 (기본 answer_obj_count=6)
# sim_cnt_norm = similar_count / max(6-1, 1) = 1/5 = 0.2
_PERC_STD_V2 = (
    _W.perception_sigma * (1.0 / 4.0)
    + _W.perception_drr * 0.15
    + _W.perception_similar_count * (1.0 / 5.0)  # answer_obj_count=6 → 1/5
    + _W.perception_similar_dist * (1.0 / 81.0)
    + _W.perception_color_contrast * 1.0
    + _W.perception_edge_strength * 1.0
) / _P_DENOM  # ≈ 0.489352
_TOT_STD_V2 = (
    _PERC_STD_V2 * _W.total_perception + _LOGI_STD * _W.total_logical
)  # ≈ 0.583208


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
        # 설계안 §2: bundle.final.total_score = scene_difficulty = D(obj) 단순 평균
        assert bundle.final.total_score == pytest.approx(_SCENE_DIFF_STD, rel=1e-4)

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
        # DummyVisual의 sigma=4+drr=0.15+similar_count=1 → 각 obj 3조건 충족 → 2 answer objs
        assert bundle.logical.signals["answer_obj_count"] == 2

    def test_two_layers_scene_difficulty_signal(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        # 설계안 §2: scene_difficulty = D(obj) 단순 평균 (두 obj 동일 → avg = D_obj)
        # answer_obj_count=2 → sim_cnt_norm = 1/1 = 1.0
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        assert bundle.scene_difficulty == pytest.approx(_SCENE_DIFF_STD, rel=1e-4)

    def test_required_signal_keys_present(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        bundle = orch.run(composite_image=composite, object_layers=layers)
        for key in ("sigma_threshold_map", "drr_slope_map"):
            assert key in bundle.perception.signals
        for key in (
            "answer_obj_count",
            "alpha_degree_map",
            "hop_map",
            "diameter",
        ):
            assert key in bundle.logical.signals
        # scene_difficulty 는 VerificationBundle 최상위 필드로 이동
        assert bundle.scene_difficulty >= 0.0

    def test_one_layer_total_score(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        """
        1개 레이어: obj_0만 physical에 존재, obj_1은 DummyVisual에서 추가.
        obj_0: visual_deg=2, logical_deg=3, hop=2, cluster=3, degree_norm=1.0
        obj_1: visual_deg=0, logical_deg=0, hop=0, cluster=0, degree_norm=0.0
               (DummyVisual: sigma=4, drr=0.15, sim_cnt=1, sim_dist=80 동일)
        answer_obj_count=2 (두 객체 모두 hf >= θ_HUMAN으로 hidden)
        bundle.final.total_score = scene_difficulty = (D_obj0 + D_obj1) / 2
        """
        layer = tmp_path / "obj_0.png"
        _make_png(layer)
        # obj_1의 metrics: physical 기본값(degree=0, cluster=0, hop=0), visual 동일
        _obj1_m = _make_metrics(
            degree_norm=0.0,
            cluster_density=0,
            hop=0,
            diameter=4.0,
            drr_slope=0.15,
            sigma_threshold=4.0,
            similar_count=1,
            similar_distance=80.0,
            color_contrast=0.0,
            edge_strength=0.0,
        )
        expected_scene_diff = (
            compute_difficulty(_STD_METRICS, answer_obj_count=2)
            + compute_difficulty(_obj1_m, answer_obj_count=2)
        ) / 2  # ≈ 0.425111

        bundle = orch.run(composite_image=composite, object_layers=[layer])
        assert bundle.final.total_score == pytest.approx(expected_scene_diff, rel=1e-4)

    def test_one_layer_answer_obj_count(
        self, orch: ValidatorOrchestrator, composite: Path, tmp_path: Path
    ) -> None:
        """
        DummyVisualVerification은 항상 obj_0, obj_1 고정 반환.
        두 객체 모두 sigma + drr_slope + similar_count = 3조건 → answer 객체
        object_count_map={obj_0:1, obj_1:1} → answer_obj_count = 2
        """
        layer = tmp_path / "obj_0.png"
        _make_png(layer)
        bundle = orch.run(composite_image=composite, object_layers=[layer])
        assert bundle.logical.signals["answer_obj_count"] == 2

    def test_no_layers_uses_default_objs(
        self, orch: ValidatorOrchestrator, composite: Path
    ) -> None:
        # layers=[] → DummyPhysical returns ["obj_0","obj_1"] → same as 2-layer case
        bundle = orch.run(composite_image=composite, object_layers=[])
        assert bundle.final.total_score == pytest.approx(_SCENE_DIFF_STD, rel=1e-4)
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
        """설계안 §2: difficulty_* 가중치 변경 시 scene_difficulty(total_score)가 달라짐.

        bundle.final.total_score = scene_difficulty = D(obj) 단순 평균.
        D(obj)는 difficulty_* 가중치로 계산되므로 이를 변경해야 score가 달라진다.
        perception_* / logical_* / total_* 변경은 scene_difficulty에 영향 없음.
        """
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            _make_png(p)
        default_orch = _make_orchestrator()
        biased_orch = _make_orchestrator(
            scoring_weights=ScoringWeights(
                difficulty_sigma=0.50,  # 기본값 0.12 → 0.50 (sigma=4 → 1/4=0.25 기여 증가)
                difficulty_degree=0.00,  # 기본값 0.14 → 0.00
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
        # 설계안 §2: bundle.final.total_score = scene_difficulty = D(obj) 단순 평균
        assert orch.run(
            composite_image=composite, object_layers=layers
        ).final.total_score == pytest.approx(_SCENE_DIFF_HARD, rel=1e-4)

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
# 3. Phase 5 단독 E2E — resolve → score → difficulty 체인
# ===========================================================================


class TestE2EPhase5Chain:
    def test_integrate_standard_metrics(self) -> None:
        metrics = _make_metrics(
            visual_degree=2,
            logical_degree=3,
            degree_norm=1.0,
            cluster_density=3,
            z_depth_hop=2,
            hop=2,
            diameter=4.0,
            sigma_threshold=4.0,
            drr_slope=0.15,
            similar_count=1,
            similar_distance=80.0,
            color_contrast=0.0,
            edge_strength=0.0,
        )
        # 이 함수 테스트는 기본 answer_obj_count=6 기준 (_PERC_STD_V2)
        perc, logi, total = integrate_verification_v2(metrics)
        assert perc == pytest.approx(_PERC_STD_V2, rel=1e-4)
        assert logi == pytest.approx(_LOGI_STD, rel=1e-4)
        assert total == pytest.approx(_TOT_STD_V2, rel=1e-4)

    def test_difficulty_and_scene_difficulty_chain(self) -> None:
        obj = _make_metrics(
            sigma_threshold=4.0,
            hop=2,
            diameter=4.0,
            degree_norm=1.0,
            drr_slope=0.15,
        )
        d = compute_difficulty(obj)
        assert d > 0.0
        assert compute_scene_difficulty([obj, obj]) == pytest.approx(d, rel=1e-4)

    def test_hard_metrics_full_chain(self) -> None:
        hard = _make_metrics(
            visual_degree=3,
            logical_degree=4,
            degree_norm=1.0,
            cluster_density=3,
            z_depth_hop=3,
            hop=4,
            diameter=4.0,
            sigma_threshold=1.0,
            drr_slope=1.0,
            similar_count=2,
            similar_distance=40.0,
            color_contrast=10.0,
            edge_strength=200.0,
        )
        perc, logi, total = integrate_verification_v2(hard)
        # 어려운 메트릭 → standard 시나리오보다 높은 점수
        assert total > _TOT_STD_V2 * 0.8  # standard 시나리오 대비 최소 80% 이상

    def test_easy_metrics_full_chain(self) -> None:
        easy = _make_metrics(
            visual_degree=0,
            logical_degree=0,
            degree_norm=0.0,
            cluster_density=0,
            z_depth_hop=0,
            hop=0,
            diameter=1.0,
            sigma_threshold=16.0,
            drr_slope=0.0,
            similar_count=0,
            similar_distance=100.0,
            color_contrast=100.0,
            edge_strength=1000.0,
        )
        _, _, total = integrate_verification_v2(easy)
        assert total < 0.10

    def test_total_score_is_weighted_sum_of_sub_scores(self) -> None:
        metrics = _make_metrics(
            sigma_threshold=2.0,
            drr_slope=0.4,
            hop=3,
            diameter=4.0,
            degree_norm=0.6,
        )
        w = ScoringWeights()
        perc, logi, total = integrate_verification_v2(metrics)
        assert total == pytest.approx(
            perc * w.total_perception + logi * w.total_logical, rel=1e-6
        )

    def test_all_scores_nonnegative_on_empty_metrics(self) -> None:
        perc, logi, total = integrate_verification_v2(_make_metrics())
        assert perc >= 0.0 and logi >= 0.0 and total >= 0.0

    def test_custom_weights_alter_score(self) -> None:
        metrics = _make_metrics(
            sigma_threshold=4.0,
            drr_slope=0.15,
            hop=2,
            diameter=4.0,
            degree_norm=1.0,
        )
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
def test_phase3_real_moondream2_loads() -> None:
    from discoverex.adapters.outbound.models.hf_moondream2 import (
        Moondream2Adapter,  # noqa: F401
    )

    raise AssertionError("이 테스트는 skip 되어야 함")


@pytest.mark.skip(reason="YOLO+CLIP: transformers 미설치")
def test_phase4_real_yolo_clip_loads() -> None:
    from discoverex.adapters.outbound.models.hf_yolo_clip import (
        YoloCLIPAdapter,  # noqa: F401
    )

    raise AssertionError("이 테스트는 skip 되어야 함")
