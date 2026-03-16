"""WeightFitter — ScoringWeights 학습 루프.

이 모듈은 engine/ 의 추론 코드와 독립적으로 동작하는 학습 전용 코드이다.
학습 결과(weights.json)만 engine/conf/validator.yaml 의 weights_path 에 지정해
추론 시 사용하며, 이 파일 자체는 추론 환경에 포함되지 않아도 된다.

파라미터 영역 구분
------------------
학습 가능 (WeightFitter 최적화 대상):
  D(obj) difficulty_* 9개 — scene_difficulty 에 직접 관여.
  합이 1.0 이 되도록 정규화하여 최적화한다.

동결 (frozen):
  is_hidden 판정 가중치 (HF_W, AF_W): hidden.py 상수
  integrate_verification_v2 scoring 가중치 (perception_*, logical_*, total_*)
  PHASE 1~4 모델 파라미터 (YAML에서 수동 조정)

손실 함수 (설계안 §5)
----------------------
label=1이면 scene_difficulty ∈ [difficulty_min, difficulty_max] 목표.
범위 밖으로 벗어난 거리에 비례하는 hinge loss:
  label=True  → loss = max(0, difficulty_min - D_obj) + max(0, D_obj - difficulty_max)
  label=False → loss = max(0, margin - max(D_obj - difficulty_max,
                                           difficulty_min - D_obj))

최적화 알고리즘
---------------
scipy.optimize.minimize — Nelder-Mead (gradient-free, GPU 불필요)

입력 데이터 형식 (bundle_to_jsonl.py 출력)
------------------------------------------
JSONL 한 줄 = hidden_object 1개:
  { "degree_norm": float, "cluster_density_norm": float,
    "hop_diameter": float, "drr_slope_norm": float,
    "sigma_threshold_norm": float, "similar_count_norm": float,
    "similar_distance_norm": float, "color_contrast_norm": float,
    "edge_strength_norm": float, "label": int }
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

_ENGINE_SRC = Path(__file__).resolve().parent.parent
if str(_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SRC))

from discoverex.domain.services.verification import ScoringWeights  # noqa: E402

# 최적화할 가중치 키 (D(obj) 수식과 1:1 대응)
_DIFFICULTY_KEYS: list[str] = [
    "difficulty_degree",
    "difficulty_cluster",
    "difficulty_hop",
    "difficulty_drr",
    "difficulty_sigma",
    "difficulty_similar_count",
    "difficulty_similar_dist",
    "difficulty_color_contrast",
    "difficulty_edge_strength",
]

# 입력 signals 키 (D(obj) 수식에서 각 가중치와 대응하는 순서)
_SIGNAL_KEYS: list[str] = [
    "degree_norm",
    "cluster_density_norm",
    "hop_diameter",
    "drr_slope_norm",
    "sigma_threshold_norm",
    "similar_count_norm",
    "similar_distance_norm",
    "color_contrast_norm",
    "edge_strength_norm",
]


class WeightFitter:
    """레이블 데이터를 이용해 ScoringWeights 의 difficulty_* 가중치를 최적화한다."""

    def fit(
        self,
        labeled: list[tuple[dict, bool]],
        init_weights: ScoringWeights | None = None,
        margin: float = 0.05,
        difficulty_min: float = 0.1,
        difficulty_max: float = 0.9,
        max_iter: int = 5000,
    ) -> ScoringWeights:
        """레이블 데이터로 ScoringWeights.difficulty_* 를 최적화해서 반환한다.

        Parameters
        ----------
        labeled:
            (signals_dict, label) 쌍의 리스트.
            signals_dict 키는 _SIGNAL_KEYS 9개 (bundle_to_jsonl.py 출력).
        init_weights:
            초기 가중치. None 이면 ScoringWeights() 기본값 사용.
        margin:
            label=False 일 때 범위 경계 밖 안전 여유.
        difficulty_min:
            설계안 §3 난이도 하한. 기본 0.1.
        difficulty_max:
            설계안 §3 난이도 상한. 기본 0.9.
        max_iter:
            Nelder-Mead 최대 반복 횟수. 기본 5000.

        Returns
        -------
        최적화된 ScoringWeights.
        difficulty_* 만 갱신; 나머지는 init_weights 값을 그대로 유지.
        """
        if not labeled:
            return init_weights or ScoringWeights()

        w0 = init_weights or ScoringWeights()
        x0 = np.array([getattr(w0, k) for k in _DIFFICULTY_KEYS], dtype=float)

        records: list[tuple[np.ndarray, bool]] = [
            (
                np.array(
                    [float(sd.get(k, 0.0)) for k in _SIGNAL_KEYS], dtype=float
                ),
                bool(lbl),
            )
            for sd, lbl in labeled
        ]

        def _loss(x: np.ndarray) -> float:
            x_pos = np.clip(x, 1e-6, None)
            w = x_pos / (x_pos.sum() + 1e-9)
            loss = 0.0
            for sig, label in records:
                d = float(np.dot(w, sig))
                if label:
                    loss += max(0.0, difficulty_min - d) + max(0.0, d - difficulty_max)
                else:
                    dist_out = max(d - difficulty_max, difficulty_min - d)
                    loss += max(0.0, margin - dist_out)
            return loss / len(records)

        result = minimize(
            _loss, x0,
            method="Nelder-Mead",
            options={"maxiter": max_iter, "xatol": 1e-5, "fatol": 1e-5},
        )

        x_opt = np.clip(result.x, 1e-6, None)
        x_norm = x_opt / (x_opt.sum() + 1e-9)

        return ScoringWeights(
            perception_sigma=w0.perception_sigma,
            perception_drr=w0.perception_drr,
            perception_similar_count=w0.perception_similar_count,
            perception_similar_dist=w0.perception_similar_dist,
            perception_color_contrast=w0.perception_color_contrast,
            perception_edge_strength=w0.perception_edge_strength,
            logical_hop=w0.logical_hop,
            logical_degree=w0.logical_degree,
            logical_cluster=w0.logical_cluster,
            total_perception=w0.total_perception,
            total_logical=w0.total_logical,
            difficulty_degree=float(x_norm[0]),
            difficulty_cluster=float(x_norm[1]),
            difficulty_hop=float(x_norm[2]),
            difficulty_drr=float(x_norm[3]),
            difficulty_sigma=float(x_norm[4]),
            difficulty_similar_count=float(x_norm[5]),
            difficulty_similar_dist=float(x_norm[6]),
            difficulty_color_contrast=float(x_norm[7]),
            difficulty_edge_strength=float(x_norm[8]),
        )
