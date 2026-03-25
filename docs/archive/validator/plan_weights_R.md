# Validator 가중치 설계 — 구현 현황 리뷰 (R)

> 이 문서는 `plan_weights.md`에서 계획한 내용이 실제로 어떻게 구현되었는지,
> 추론(inference)과 학습(training)이 어떻게 분리되어 독립적으로 동작하는지를
> 실제 코드 기준으로 기록한다.

---

## 1. 파라미터 전체 지도

아래 표는 Validator 파이프라인에 존재하는 **모든 조정 가능 수치**를
성격별로 분류한 것이다.

```
┌─────────────────────────────────────────────────────────────────────┐
│ A. 학습 가능 (WeightFitter 최적화 대상)                              │
│    미분 가능 연속 함수 → Nelder-Mead gradient-free 최적화           │
│                                                                      │
│    PHASE 4  ScoringWeights (engine/src/discoverex/                  │
│             domain/services/verification.py)                        │
│                                                                      │
│    scoring 5개 (WeightFitter 최적화):                               │
│      perception_sigma   = 0.50  (PHASE 3 σ 항 가중치)              │
│      perception_drr     = 0.50  (PHASE 3 DRR 항 가중치)            │
│      logical_hop        = 0.55  (PHASE 2 hop/d 항 가중치)          │
│      logical_degree     = 0.45  (PHASE 2 degree² 항 가중치)        │
│      total_perception   = 0.45  (total 집계 가중치)                │
│      [total_logical = 1.0 − total_perception 으로 자동 파생]       │
│                                                                      │
│    difficulty 6개 (현재 init_weights 값 고정, 확장 가능):          │
│      difficulty_occlusion   = 0.25                                  │
│      difficulty_sigma       = 0.20                                  │
│      difficulty_hop         = 0.20                                  │
│      difficulty_degree      = 0.15                                  │
│      difficulty_drr         = 0.20                                  │
│      difficulty_interaction = 0.10                                  │
├─────────────────────────────────────────────────────────────────────┤
│ B. 동결(frozen) + YAML 변수화                                        │
│    step function 포함 → 미분 불가, WeightFitter 제외               │
│    YAML 수치 변경으로 수동 실험 가능                                │
│                                                                      │
│    PHASE 1  cluster_radius_factor = 0.5                             │
│             (conf/models/physical_extraction/mobilesam.yaml)        │
│             cluster_radius = mean_dist × factor                     │
│             → cluster_density_map (이웃 객체 수) 결정              │
│                                                                      │
│    PHASE 3  iou_match_threshold = 0.3                               │
│             (conf/models/visual_verification/yolo_clip.yaml)        │
│             IoU < threshold → 객체 사라짐으로 판정                  │
│             → sigma_threshold_map 결정                              │
│                                                                      │
│    PHASE 3  sigma_levels = [1.0, 2.0, 4.0, 8.0, 16.0]             │
│             (conf/models/visual_verification/yolo_clip.yaml)        │
│             이산 블러 격자 — feature space 자체를 정의             │
├─────────────────────────────────────────────────────────────────────┤
│ C. 알고리즘 정의 상수 (변경 불필요)                                  │
│    수학적 정의에서 도출 — 튜닝 대상 아님                           │
│                                                                      │
│    PHASE 1  occlusion 판정: alpha > 0 (픽셀 투명도 기준)           │
│    PHASE 2  root 판정: in_degree == 0 (그래프 이론 정의)           │
│    PHASE 2  diameter 하한: max(diameter, 1.0) (0-division 방지)    │
│    PHASE 4  is_hidden_min_conditions = 2 (conf/validator.yaml)     │
│    PHASE 4  pass_threshold = 0.35 (conf/validator.yaml)            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 추론 파이프라인 — 학습과의 독립성

### 2-1. 데이터 흐름

```
이미지 파일 (composite.png + obj_*.png)
        │
        ▼
[PHASE 1] MobileSAMAdapter.extract()
          · cluster_radius_factor (frozen, YAML)
          → PhysicalMetadata
            occlusion_map, z_depth_hop_map, cluster_density_map,
            euclidean_distance_map, regions
        │
        ▼ (PhysicalMetadata 전달 → bbox로 VLM 프롬프트 구성)
[PHASE 2] Moondream2Adapter.extract(composite, physical)
          · 신규 하드코딩 수치 없음
          → LogicalStructure
            degree_map, hop_map, diameter, relations
        │
        ▼
[PHASE 3] YoloCLIPAdapter.verify()
          · iou_match_threshold (frozen, YAML)
          · sigma_levels (frozen, YAML)
          → VisualVerification
            sigma_threshold_map, detail_retention_rate_map
        │
        ▼
[PHASE 4] 순수 수식 계산 (모델 로드 없음)
          · ScoringWeights (학습 가능, YAML 또는 weights.json)
          integrate_verification_v2()  → perception, logical, total score
          compute_scene_difficulty()   → difficulty
          resolve_answer()             → 정답 객체 식별
          → VerificationBundle
```

### 2-2. PHASE 2가 PHASE 1 출력을 활용하는 방식

```python
# orchestrator.py
physical = self._run_phase1(composite_image, object_layers)
logical  = self._run_phase2(composite_image, physical)   # physical 주입
```

`Moondream2Adapter._build_prompt(physical)`:
```
"The scene contains these objects:
  obj_0 at bbox [0.12, 0.08, 0.35, 0.42];
  obj_1 at bbox [0.55, 0.20, 0.28, 0.38]. ..."
```

PHASE 1의 `regions` (SAM이 추출한 정밀 bbox)가 VLM 프롬프트에 주입되어
PHASE 2의 공간 관계 추론이 물리적 위치 정보를 기반으로 동작한다.
이후 그래프 계산(degree, hop, diameter)은 전부 CPU에서 수행된다.

### 2-3. ScoringWeights 주입 경로

```
conf/validator.yaml
  weights_path: null          ← null이면 weights: 섹션 사용
  weights:
    perception_sigma: 0.50
    ...
        │
        ▼
factory.py: _build_scoring_weights(cfg)
  if cfg.weights_path:
      ScoringWeights.model_validate_json(path.read_text())   # JSON 로드
  else:
      ScoringWeights(**cfg.weights.model_dump())             # YAML 로드
        │
        ▼
ValidatorOrchestrator(scoring_weights=...)
  self._weights = scoring_weights or ScoringWeights()
        │
        ▼
_run_phase4() → integrate_verification_v2(metrics, threshold, w)
```

### 2-4. ML 폴더와의 의존 관계

```
discoverex/ 패키지        engine/src/ML/ 패키지
──────────────────        ─────────────────────
(추론 코드)               (학습 전용 코드)

                ▶ import discoverex.domain.services.verification.ScoringWeights
                ▶ import discoverex.domain.services.verification.integrate_verification_v2

discoverex/ ─────────────────────────────────────────────────────▶ (import 없음)
```

`discoverex/` 패키지 어디에도 `ML` 모듈을 import하는 코드가 없다.
`engine/src/ML/`을 통째로 삭제해도 추론 파이프라인은 영향 없이 동작한다.
두 영역의 교환점은 오직 **`weights.json` 파일**이다.

---

## 3. 학습 파이프라인 — 구현 현황

### 3-1. 학습 입력 데이터

WeightFitter가 받는 입력은 **이미 추출된 metrics dict + label** 쌍이다.
이미지 자체는 입력으로 들어오지 않는다.

```jsonl
{"metrics": {"sigma_threshold": 2.0, "detail_retention_rate": 0.3,
             "hop": 2, "diameter": 4.0, "degree_norm": 0.7}, "label": true}
{"metrics": {"sigma_threshold": 8.0, "detail_retention_rate": 0.9,
             "hop": 0, "diameter": 4.0, "degree_norm": 0.1}, "label": false}
```

실제 이미지로 학습 데이터를 만들려면:

```
이미지 → PHASE 1~3 실행 → per-object metrics 추출 → label 부착 → JSONL 저장
```

이 변환 단계는 현재 구현에 포함되지 않으며,
`ValidatorOrchestrator.run()`으로 `VerificationBundle`을 얻은 뒤
그 안의 signals에서 metrics를 수동으로 수집해야 한다.

### 3-2. 손실 함수 — hinge loss

```
label=True  → loss = max(0, threshold + margin − score)
              (점수가 threshold+margin 미만이면 패널티)

label=False → loss = max(0, score − (threshold − margin))
              (점수가 threshold−margin 초과이면 패널티)

평균 loss = Σ loss / N
```

- `margin` 기본값 = 0.05 (threshold 양쪽 5% 마진)
- `pass_threshold` 기본값 = 0.35

### 3-3. 최적화 알고리즘

`scipy.optimize.minimize` — Nelder-Mead (gradient-free)

선택 이유:
- hinge loss의 `max()` 와 step function들이 미분 불가능한 지점을 포함
- GPU 불필요, CPU만으로 수렴 (파라미터 5개로 충분히 빠름)
- `total_perception`만 최적화하고 `total_logical = 1 − total_perception`으로 파생
  → total_perception + total_logical = 1.0 제약 자동 충족

### 3-4. 학습 흐름

```
labeled.jsonl (PHASE 1~3 결과를 수동 수집한 metrics)
        │
        ▼
fit_weights.py CLI (engine/src/ML/fit_weights.py)
  python engine/src/ML/fit_weights.py \
      --labeled-jsonl data/labeled.jsonl \
      --weights-out   ml_output/weights.json \
      [--weights-in   ml_output/weights.json]   # 이어 학습
      [--pass-threshold 0.35]
      [--margin 0.05]
      [--max-iter 5000]
        │
        ▼
WeightFitter.fit(labeled, init_weights) (engine/src/ML/weight_fitter.py)
  scipy Nelder-Mead: x = [perception_sigma, perception_drr,
                           logical_hop, logical_degree, total_perception]
        │  최적화 완료
        ▼
ScoringWeights (최적화된 5개 + difficulty_* 6개는 init값 유지)
        │
        ▼
weights.json 저장
```

### 3-5. 학습 결과를 추론에 반영

```yaml
# conf/validator.yaml
weights_path: /path/to/ml_output/weights.json   # ← 이 줄 하나만 추가
```

이후 `build_validator_context()` 호출 시 `factory._build_scoring_weights()`가
JSON 파일을 읽어 `ScoringWeights`를 구성하고 `ValidatorOrchestrator`에 주입한다.
YAML의 `weights:` 섹션은 무시된다.

---

## 4. frozen hyperparam 수동 실험 방법

동결된 파라미터(B 영역)는 YAML만 수정하면 재실행 시 즉시 반영된다.

### PHASE 1: cluster_radius_factor 조정

```yaml
# conf/models/physical_extraction/mobilesam.yaml
cluster_radius_factor: 0.5   # 기본값
# cluster_radius_factor: 0.3  # 좁은 클러스터 → 이웃 판정 더 엄격
# cluster_radius_factor: 0.8  # 넓은 클러스터 → 이웃 판정 더 관대
```

효과: `cluster_density_map` 값이 달라짐 → `resolve_answer()`의
`neighbor_count >= 3` 조건 충족 여부가 바뀜 → answer 객체 집합이 달라짐.

### PHASE 3: iou_match_threshold 조정

```yaml
# conf/models/visual_verification/yolo_clip.yaml
iou_match_threshold: 0.3    # 기본값
# iou_match_threshold: 0.5  # 엄격 → 같은 σ에서 더 쉽게 "사라짐"으로 판정
# iou_match_threshold: 0.1  # 관대 → 더 높은 σ까지 버텨야 사라짐 판정
```

효과: `sigma_threshold_map` 값이 달라짐 →
`sigma` 가 낮을수록 perception score 상승 (1/σ 항).

### PHASE 3: sigma_levels 조정

```yaml
sigma_levels: [1.0, 2.0, 4.0, 8.0, 16.0]        # 기본 (5단계)
# sigma_levels: [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]  # 세밀한 저σ 구간 추가
# sigma_levels: [2.0, 8.0, 32.0]                  # 거친 3단계
```

효과: 측정 격자가 바뀌므로 sigma_threshold가 취할 수 있는 값 집합이 달라짐.

---

## 5. 계획(plan_weights.md) → 구현 대응표

| 계획 항목 | 구현 파일 | 상태 |
|----------|----------|------|
| ScoringWeights Pydantic 모델 (12 필드) | `domain/services/verification.py` | ✅ 완료 |
| integrate_verification_v2 정규화 수식 | `domain/services/verification.py` | ✅ 완료 |
| compute_difficulty / compute_scene_difficulty | `domain/services/verification.py` | ✅ 완료 |
| ValidatorWeightsConfig (config 레이어) | `config/schema.py` | ✅ 완료 |
| weights_path 로드 분기 | `bootstrap/factory.py` | ✅ 완료 |
| orchestrator scoring_weights 주입 | `application/use_cases/validator/orchestrator.py` | ✅ 완료 |
| conf/validator.yaml weights 섹션 | `conf/validator.yaml` | ✅ 완료 |
| WeightFitter (hinge loss + Nelder-Mead) | `engine/src/ML/weight_fitter.py` | ✅ 완료 |
| fit_weights.py CLI 스크립트 | `engine/src/ML/fit_weights.py` | ✅ 완료 |
| cluster_radius_factor 변수화 | `hf_mobilesam.py` + `mobilesam.yaml` | ✅ 완료 |
| iou_match_threshold 변수화 | `hf_yolo_clip.py` + `yolo_clip.yaml` | ✅ 완료 |
| sigma_levels 변수화 | `hf_yolo_clip.py` + `yolo_clip.yaml` | ✅ (기존부터) |
| E2E 테스트 (Dummy 어댑터) | `tests/test_validator_e2e.py` | ✅ 완료 |
| 전체 테스트 통과 | — | ✅ 81 passed, 7 skipped |

### 계획 대비 달라진 점

| 계획 | 실제 | 이유 |
|------|------|------|
| `adapters/inbound/cli/main.py`에 fit-weights 커맨드 추가 | `engine/src/ML/fit_weights.py`로 독립 스크립트 분리 | 학습 코드를 추론 엔진과 완전 분리하기 위해 ML 폴더로 이동 |
| `domain/services/weight_fitter.py` 위치 | `engine/src/ML/weight_fitter.py` | 동일 이유 |

---

## 6. 현재 구현의 한계와 향후 확장 가능성

| 항목 | 현재 | 향후 가능한 방향 |
|------|------|----------------|
| 학습 입력 | metrics JSONL (수동 수집) | 이미지 → PHASE 1~3 자동 실행 후 JSONL 저장 스크립트 추가 |
| difficulty_* 학습 | 고정 (init_weights 유지) | WeightFitter `_SCORED_KEYS`에 추가하면 즉시 확장 가능 |
| frozen hyperparam 실험 자동화 | YAML 수동 수정 | grid search 스크립트 추가 (cluster_radius_factor × iou_match_threshold) |
| 딥러닝 파라미터 (SAM/Moondream2/YOLO/CLIP) | 미구현 | 별도 fine-tuning 파이프라인 필요 (gradient-based, phase별 labeled dataset) |
