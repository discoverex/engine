"""WeightFitter — ScoringWeights 학습 루프.

이 모듈은 engine/ 의 추론 코드와 독립적으로 동작하는 학습 전용 코드이다.
학습 결과(weights.json)만 engine/conf/validator.yaml 의 weights_path 에 지정해
추론 시 사용하며, 이 파일 자체는 추론 환경에 포함되지 않아도 된다.

파라미터 영역 구분
------------------
┌─────────────────────────────────────────────────────────────────┐
│ 학습 가능 (WeightFitter 최적화 대상)                              │
│   PHASE 4 ScoringWeights — 연속 미분 가능, Nelder-Mead 최적화    │
│     perception_sigma, perception_drr                             │
│     logical_hop, logical_degree                                  │
│     total_perception  (total_logical = 1 - total_perception)     │
├─────────────────────────────────────────────────────────────────┤
│ 동결 (frozen) — step function → 미분 불가, WeightFitter 제외     │
│   PHASE 1  cluster_radius_factor  (conf/models/.../mobilesam.yaml) │
│             cluster_radius = mean_dist × factor                  │
│   PHASE 3  iou_match_threshold    (conf/models/.../yolo_clip.yaml) │
│             IoU < threshold → 객체 사라짐으로 판정               │
│   PHASE 3  sigma_levels           (conf/models/.../yolo_clip.yaml) │
│             이산 블러 격자 — feature space 자체를 정의           │
│                                                                   │
│   → YAML에서 수동으로 값을 바꾸면 파이프라인 전체에 반영됨       │
├─────────────────────────────────────────────────────────────────┤
│ 미학습 고정 (difficulty_* 6개)                                    │
│   난이도 진단용 가중치 — 학습 필요 시 init_weights 로 초기화 후  │
│   WeightFitter 확장 가능 (현재는 init_weights 값 그대로 유지)    │
└─────────────────────────────────────────────────────────────────┘

학습 대상
----------
scoring 관련 5개 파라미터:
  perception_sigma, perception_drr, logical_hop, logical_degree, total_perception
total_logical 은 1.0 - total_perception 으로 자동 파생 (합 = 1.0 보장).
difficulty_* 6개는 난이도 진단용이므로 기본값 유지.

손실 함수
----------
hinge loss:
  label=True  → loss = max(0, threshold + margin - score)
  label=False → loss = max(0, score - (threshold - margin))

최적화 알고리즘
---------------
scipy.optimize.minimize — Nelder-Mead (gradient-free, GPU 불필요)

사용 예
-------
    python engine/src/ML/weight_fitter.py
    또는 engine/src/ML/fit_weights.py 스크립트 참조
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

# engine 패키지 경로를 sys.path 에 추가 (editable install 없이도 동작)
# 이 파일 위치: engine/src/ML/weight_fitter.py
# engine/src/ 는 parent.parent
_ENGINE_SRC = Path(__file__).resolve().parent.parent
if str(_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SRC))

from discoverex.domain.services.verification import (  # noqa: E402
    ScoringWeights,
    integrate_verification_v2,
)

# 최적화할 가중치 키 순서 (x 벡터 인덱스와 1:1 대응)
_SCORED_KEYS: list[str] = [
    "perception_sigma",
    "perception_drr",
    "logical_hop",
    "logical_degree",
    "total_perception",  # total_logical = 1.0 - total_perception 으로 파생
]


class WeightFitter:
    """레이블 데이터를 이용해 ScoringWeights 의 scoring 관련 가중치를 최적화한다.

    사용 예
    -------
    >>> fitter = WeightFitter()
    >>> labeled = [
    ...     ({"sigma_threshold": 2.0, "detail_retention_rate": 0.3,
    ...       "hop": 2, "diameter": 4.0, "degree_norm": 0.7}, True),
    ...     ({"sigma_threshold": 8.0, "detail_retention_rate": 0.9,
    ...       "hop": 0, "diameter": 4.0, "degree_norm": 0.1}, False),
    ... ]
    >>> optimised = fitter.fit(labeled, pass_threshold=0.35)
    >>> print(optimised.model_dump_json(indent=2))
    """

    def fit(
        self,
        labeled: list[tuple[dict, bool]],
        init_weights: ScoringWeights | None = None,
        margin: float = 0.05,
        pass_threshold: float = 0.35,
        max_iter: int = 5000,
    ) -> ScoringWeights:
        """레이블 데이터로 ScoringWeights 를 최적화해서 반환한다.

        Parameters
        ----------
        labeled:
            (obj_metrics dict, 정답_pass bool) 쌍의 리스트.
            obj_metrics 키는 integrate_verification_v2 와 동일.
        init_weights:
            초기 가중치. None 이면 ScoringWeights() 기본값 사용.
        margin:
            hinge loss 의 안전 마진. 기본 0.05.
            label=True  이면 threshold+margin 이상 달성이 목표.
            label=False 이면 threshold-margin 미만 달성이 목표.
        pass_threshold:
            판정 기준선. 기본 0.35.
        max_iter:
            Nelder-Mead 최대 반복 횟수. 기본 5000.

        Returns
        -------
        최적화된 ScoringWeights.
        difficulty_* 는 init_weights 값을 그대로 유지.
        """
        if not labeled:
            return init_weights or ScoringWeights()

        w0 = init_weights or ScoringWeights()
        x0 = np.array([getattr(w0, k) for k in _SCORED_KEYS], dtype=float)

        def _loss(x: np.ndarray) -> float:
            x_pos = np.clip(x, 1e-6, None)
            total_p = float(x_pos[4])
            total_l = max(1.0 - total_p, 1e-6)
            w = ScoringWeights(
                perception_sigma=float(x_pos[0]),
                perception_drr=float(x_pos[1]),
                logical_hop=float(x_pos[2]),
                logical_degree=float(x_pos[3]),
                total_perception=total_p,
                total_logical=total_l,
                # difficulty_* 는 초기값 유지
                difficulty_occlusion=w0.difficulty_occlusion,
                difficulty_sigma=w0.difficulty_sigma,
                difficulty_hop=w0.difficulty_hop,
                difficulty_degree=w0.difficulty_degree,
                difficulty_drr=w0.difficulty_drr,
                difficulty_interaction=w0.difficulty_interaction,
            )
            loss = 0.0
            for metrics, label in labeled:
                _, _, score = integrate_verification_v2(metrics, weights=w)
                if label:
                    loss += max(0.0, pass_threshold + margin - score)
                else:
                    loss += max(0.0, score - (pass_threshold - margin))
            return loss / len(labeled)

        result = minimize(
            _loss,
            x0,
            method="Nelder-Mead",
            options={"maxiter": max_iter, "xatol": 1e-5, "fatol": 1e-5},
        )

        x_opt = np.clip(result.x, 1e-6, None)
        total_p_opt = float(x_opt[4])
        total_l_opt = max(1.0 - total_p_opt, 1e-6)

        return ScoringWeights(
            perception_sigma=float(x_opt[0]),
            perception_drr=float(x_opt[1]),
            logical_hop=float(x_opt[2]),
            logical_degree=float(x_opt[3]),
            total_perception=total_p_opt,
            total_logical=total_l_opt,
            difficulty_occlusion=w0.difficulty_occlusion,
            difficulty_sigma=w0.difficulty_sigma,
            difficulty_hop=w0.difficulty_hop,
            difficulty_degree=w0.difficulty_degree,
            difficulty_drr=w0.difficulty_drr,
            difficulty_interaction=w0.difficulty_interaction,
        )
