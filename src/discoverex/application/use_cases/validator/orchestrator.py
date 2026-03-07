from __future__ import annotations

from pathlib import Path

from discoverex.application.ports.models import (
    BundleStorePort,
    LogicalExtractionPort,
    PhysicalExtractionPort,
    VisualVerificationPort,
)
from discoverex.domain.services.verification import (
    ScoringWeights,
    compute_scene_difficulty,
    integrate_verification_v2,
    resolve_answer,
)
from discoverex.domain.verification import (
    FinalVerification,
    VerificationBundle,
    VerificationResult,
)
from discoverex.models.types import (
    LogicalStructure,
    ModelHandle,
    PhysicalMetadata,
    ValidatorInput,
    VisualVerification,
)

_DEFAULT_SIGMA_LEVELS: list[float] = [1.0, 2.0, 4.0, 8.0, 16.0]


class ValidatorOrchestrator:
    """
    4-Phase 순차 실행 Validator — VRAM 바통 패스 전략.

    각 Phase 가 독립적으로 모델을 로드·실행·언로드하므로
    피크 VRAM 이 8 GB 예산 내에 유지된다.
    Phase 간 데이터는 JSON 직렬화 가능한 Pydantic 모델로 전달된다.
    """

    def __init__(
        self,
        physical_port: PhysicalExtractionPort,
        logical_port: LogicalExtractionPort,
        visual_port: VisualVerificationPort,
        physical_handle: ModelHandle,
        logical_handle: ModelHandle,
        visual_handle: ModelHandle,
        pass_threshold: float = 0.35,
        scoring_weights: ScoringWeights | None = None,
        sigma_levels: list[float] | None = None,
        bundle_store: BundleStorePort | None = None,
    ) -> None:
        self._physical_port = physical_port
        self._logical_port = logical_port
        self._visual_port = visual_port
        self._physical_handle = physical_handle
        self._logical_handle = logical_handle
        self._visual_handle = visual_handle
        self._pass_threshold = pass_threshold
        self._weights = scoring_weights or ScoringWeights()
        self._sigma_levels = sigma_levels or _DEFAULT_SIGMA_LEVELS
        self._bundle_store = bundle_store

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        composite_image: Path,
        object_layers: list[Path],
    ) -> VerificationBundle:
        """4개 Phase 를 모두 실행하고 최종 VerificationBundle 을 반환한다."""
        physical = self._run_phase1(composite_image, object_layers)
        logical = self._run_phase2(composite_image, physical)
        visual = self._run_phase3(composite_image)
        bundle = self._run_phase4(
            ValidatorInput(physical=physical, logical=logical, visual=visual)
        )
        if self._bundle_store is not None:
            self._bundle_store.save(bundle, composite_image, object_layers)
        return bundle

    # ------------------------------------------------------------------
    # Phase runners
    # ------------------------------------------------------------------

    def _run_phase1(
        self, composite_image: Path, object_layers: list[Path]
    ) -> PhysicalMetadata:
        self._physical_port.load(self._physical_handle)
        try:
            return self._physical_port.extract(composite_image, object_layers)
        finally:
            self._physical_port.unload()

    def _run_phase2(
        self, composite_image: Path, physical: PhysicalMetadata
    ) -> LogicalStructure:
        self._logical_port.load(self._logical_handle)
        try:
            return self._logical_port.extract(composite_image, physical)
        finally:
            self._logical_port.unload()

    def _run_phase3(self, composite_image: Path) -> VisualVerification:
        self._visual_port.load(self._visual_handle)
        try:
            return self._visual_port.verify(composite_image, self._sigma_levels)
        finally:
            self._visual_port.unload()

    def _run_phase4(self, data: ValidatorInput) -> VerificationBundle:
        """순수 계산 — 모델 로드 없음."""
        physical, logical, visual = data.physical, data.logical, data.visual
        w = self._weights

        # 모든 Phase 에 걸쳐 등장한 오브젝트 ID 합집합
        all_obj_ids: set[str] = (
            set(physical.occlusion_map)
            | set(logical.degree_map)
            | set(visual.sigma_threshold_map)
        )

        # degree 정규화를 위한 최댓값
        max_degree = max(
            (logical.degree_map.get(oid, 0) for oid in all_obj_ids), default=1
        )
        max_degree = max(max_degree, 1)

        answer_obj_metrics: list[dict[str, float | int]] = []
        per_obj_perception: list[float] = []
        per_obj_logical: list[float] = []

        for obj_id in sorted(all_obj_ids):
            metrics: dict[str, float | int] = {
                "occlusion_ratio": physical.occlusion_map.get(obj_id, 0.0),
                "sigma_threshold": visual.sigma_threshold_map.get(obj_id, 16.0),
                "degree": logical.degree_map.get(obj_id, 0),
                "degree_norm": logical.degree_map.get(obj_id, 0) / max_degree,
                "z_depth_hop": physical.z_depth_hop_map.get(obj_id, 0),
                "neighbor_count": physical.cluster_density_map.get(obj_id, 0),
                "hop": logical.hop_map.get(obj_id, 0),
                "diameter": logical.diameter,
                "detail_retention_rate": visual.detail_retention_rate_map.get(
                    obj_id, 1.0
                ),
            }
            if resolve_answer(metrics):
                answer_obj_metrics.append(metrics)
            p_score, l_score, _ = integrate_verification_v2(
                metrics, self._pass_threshold, w
            )
            per_obj_perception.append(p_score)
            per_obj_logical.append(l_score)

        # Scene 단위 집계
        avg_perception = (
            sum(per_obj_perception) / len(per_obj_perception)
            if per_obj_perception
            else 0.0
        )
        avg_logical = (
            sum(per_obj_logical) / len(per_obj_logical) if per_obj_logical else 0.0
        )
        total_score = (
            avg_perception * w.total_perception + avg_logical * w.total_logical
        )
        passed = total_score >= self._pass_threshold

        difficulty = compute_scene_difficulty(answer_obj_metrics, w)

        return VerificationBundle(
            perception=VerificationResult(
                score=avg_perception,
                **{"pass": passed},
                signals={
                    "sigma_threshold_map": visual.sigma_threshold_map,
                    "detail_retention_rate_map": visual.detail_retention_rate_map,
                },
            ),
            logical=VerificationResult(
                score=avg_logical,
                **{"pass": passed},
                signals={
                    "degree_map": logical.degree_map,
                    "hop_map": logical.hop_map,
                    "diameter": logical.diameter,
                    "answer_obj_count": len(answer_obj_metrics),
                    "scene_difficulty": difficulty,
                },
            ),
            final=FinalVerification(
                total_score=total_score,
                **{"pass": passed},
                failure_reason="" if passed else "difficulty_too_low",
            ),
        )


# ------------------------------------------------------------------
# 편의 함수
# ------------------------------------------------------------------


def run_validator(
    composite_image: Path,
    object_layers: list[Path],
    orchestrator: ValidatorOrchestrator,
) -> VerificationBundle:
    return orchestrator.run(composite_image, object_layers)
