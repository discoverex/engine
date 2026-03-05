# 가중치 변수화 및 학습 루프 계획안

## 목표

1. `integrate_verification_v2`, `compute_difficulty` 등에 하드코딩된 숫자를
   `ScoringWeights` Pydantic 모델로 집약하고 YAML로 외부 주입 가능하게 한다.
2. 레이블 데이터를 통해 가중치를 실제로 업데이트할 수 있는 **학습 루프**를 추가한다.
   초기값은 코드 기본값 또는 YAML에서 읽고, 학습 후 JSON 파일로 저장·로드한다.
3. 기존 파일과의 **충돌 지점을 모두 식별**하고 수정 방향을 명시한다.

---

## 1. 수식 구조 변경 (정규화 추가)

### 기존 문제

```
perception = 0.20 × (1/σ) + 0.20 × (1 − DRR)   → 최댓값 0.40
logical    = 0.20 × (hop/d) + 0.15 × deg²         → 최댓값 0.35
total      = perception × 0.45 + logical × 0.55   → 최댓값 0.3725
```

pass_threshold = 0.35이므로 완벽한 수치여야만 통과. 현실적 "어려운" 장면은 total ≈ 0.20 → 항상 실패.

### 변경 후 (정규화)

```
p_denom    = w_σ + w_drr                                           (0이 되면 1e-9로 보호)
perception = (w_σ × (1/σ) + w_drr × (1−DRR)) / p_denom           → [0, 1]

l_denom    = w_hop + w_deg
logical    = (w_hop × (hop/d) + w_deg × deg²) / l_denom           → [0, 1]

total      = perception × w_p + logical × w_l                     → max = w_p + w_l
```

`w_p + w_l = 1.0`이면 total 최댓값도 1.0.

### 초기 가중치 설계 검증

| 시나리오 | σ | DRR | hop/d | deg_norm | total  | 판정    |
|---------|---|-----|-------|----------|--------|---------|
| 어려움  | 2 | 0.3 | 0.50  | 0.70     | 0.543  | PASS ✓  |
| 보통    | 4 | 0.5 | 0.25  | 0.50     | 0.306  | fail ✓  |
| 쉬움    | 8 | 0.8 | 0.00  | 0.20     | 0.083  | fail ✓  |
| 더미    | 1 | 0.0 | 1.00  | 1.00     | 1.000  | PASS ✓  |

초기값:

```
# perception sub-score 가중치 (정규화 분모에 사용되므로 비율만 의미 있음)
perception_sigma = 0.50,  perception_drr = 0.50

# logical sub-score 가중치
logical_hop = 0.55,  logical_degree = 0.45

# total 집계 (합이 1.0이어야 total 최댓값 = 1.0)
total_perception = 0.45,  total_logical = 0.55

# D(obj) 항별 가중치 (정규화 없음, 절댓값 유지)
difficulty_occlusion = 0.25,  difficulty_sigma = 0.20
difficulty_hop = 0.20,        difficulty_degree = 0.15
difficulty_drr = 0.20,        difficulty_interaction = 0.10
```

---

## 2. 학습 루프 설계

### 2-1. 학습이 필요한 이유

현재 계획은 숫자를 변수(필드)로만 교체하므로, 실행 중 가중치가 바뀌지 않는다.
학습 루프가 없으면 초기값이 영구히 고정된다.
레이블 데이터(장면의 pass/fail 정답)를 모아 가중치를 업데이트해야 초기값의 한계를 극복할 수 있다.

### 2-2. 학습 대상 파라미터

12개 필드 중 학습에 실제로 의미 있는 것은 **scoring 관련 6개** (integrate_verification_v2에 쓰이는 값):

```
perception_sigma, perception_drr
logical_hop, logical_degree
total_perception, total_logical
```

difficulty_* 6개는 장면 난이도 진단용이므로 1차 학습 범위에서 제외해도 무방 (옵션).

### 2-3. 제약 조건

| 파라미터 그룹          | 제약                                    | 이유                                      |
|-----------------------|-----------------------------------------|-------------------------------------------|
| perception_sigma/drr  | 모두 ≥ 0 (비율만 의미, 합 무관)          | 수식 내부에서 합으로 정규화               |
| logical_hop/degree    | 모두 ≥ 0 (비율만 의미, 합 무관)          | 동일                                      |
| total_perception/logical | 모두 ≥ 0, **합 = 1.0** 강제           | total 최댓값을 1.0으로 유지하기 위함       |

→ 최적화 시 `total_perception`만 학습하고 `total_logical = 1.0 - total_perception`으로 파생.

### 2-4. 손실 함수

레이블 데이터: `list[tuple[dict, bool]]` — `(obj_metrics, 정답_pass)`

```
손실 = hinge loss:
  label=True  → loss = max(0, threshold + margin - total_score)   # 너무 낮으면 패널티
  label=False → loss = max(0, total_score - (threshold - margin)) # 너무 높으면 패널티

margin = 0.05 (기본값, 설정 가능)
```

binary cross-entropy 대신 hinge loss를 사용하는 이유:
- sigmoid 없이도 수치적으로 안정적
- threshold 주변 margin만 학습하면 되므로 수렴 빠름
- GPU 불필요 (scipy.optimize로 CPU만으로 처리)

### 2-5. 최적화 알고리즘

`scipy.optimize.minimize` — Nelder-Mead 방법

- 수식이 미분 불가능한 max() 포함 → gradient-free 방법 선택
- GPU 불필요, 수백~수천 개 장면 처리 가능
- 파라미터 개수 ≤ 12개이므로 충분히 빠름

### 2-6. 학습 흐름

```
레이블 JSONL 파일
  ({"metrics": {...}, "label": true/false} 한 줄씩)
        │
        ▼
WeightFitter.fit(labeled_data, init_weights)
        │  scipy Nelder-Mead 최적화
        ▼
최적화된 ScoringWeights
        │
        ▼
JSON 파일로 저장 (weights.json)
        │
        ▼
다음 실행 시 factory.py 에서 로드 → ValidatorOrchestrator 에 주입
```

### 2-7. 새로 추가할 파일

#### `domain/services/weight_fitter.py`

```python
class WeightFitter:
    SCORED_KEYS = [
        "perception_sigma", "perception_drr",
        "logical_hop", "logical_degree",
        "total_perception",   # total_logical = 1.0 - total_perception 으로 파생
    ]

    def fit(
        self,
        labeled: list[tuple[dict, bool]],
        init_weights: ScoringWeights | None = None,
        margin: float = 0.05,
        pass_threshold: float = 0.35,
    ) -> ScoringWeights:
        """레이블 데이터로 ScoringWeights 를 최적화해서 반환."""
        ...

    def _loss(x, labeled, margin, threshold) -> float:
        """hinge loss 계산."""
        ...
```

#### `adapters/inbound/cli/main.py` — 새 커맨드 추가

```
discoverex fit-weights
  --labeled-jsonl  PATH     # {"metrics":{...}, "label": true} 형식 JSONL
  --weights-in     PATH?    # 초기값 JSON (없으면 ScoringWeights 기본값 사용)
  --weights-out    PATH     # 학습된 가중치를 저장할 JSON 경로
  --pass-threshold FLOAT    # 기본 0.35
  --margin         FLOAT    # hinge 마진, 기본 0.05
```

출력: `{"weights_path": "...", "final_loss": 0.012, "n_samples": 120}`

### 2-8. 가중치 영속성 (저장/로드)

별도 어댑터 없이 단순 JSON 파일로 처리:

```python
# 저장
Path(weights_out).write_text(weights.model_dump_json(indent=2))

# 로드
ScoringWeights.model_validate_json(Path(weights_in).read_text())
```

`ValidatorPipelineConfig` 에 `weights_path: str | None = None` 필드 추가:
- `weights_path`가 지정되면 factory에서 JSON 파일 로드 → YAML `weights:` 섹션 무시
- 미지정이면 YAML `weights:` 섹션 또는 코드 기본값 사용

---

## 3. 아키텍처 흐름 (학습 포함)

```
[추론 경로]
YAML weights: / weights_path: (weights.json)
        │
        ▼
ValidatorWeightsConfig  [config/schema.py]
        │  factory: ScoringWeights(**cfg.weights.model_dump())
        │  또는:    ScoringWeights.model_validate_json(weights_path)
        ▼
ScoringWeights → ValidatorOrchestrator → _run_phase4
        │
        ├─► integrate_verification_v2(metrics, threshold, weights)
        ├─► compute_difficulty(metrics, weights)
        └─► compute_scene_difficulty(objs, weights)

[학습 경로]
labeled.jsonl
        │
        ▼
fit-weights CLI → WeightFitter.fit(labeled, init_weights)
        │  scipy Nelder-Mead
        ▼
weights.json (저장)
        │
        ▼ (다음 실행 시 weights_path 로 로드)
ValidatorOrchestrator
```

---

## 4. 충돌 검토 — 기존 파일과의 불일치 지점

소스를 직접 확인한 결과, 아래 지점들이 계획과 충돌한다.

### 4-1. `tests/test_validator_pipeline_smoke.py:31`

```python
# 현재 (충돌)
return ValidatorOrchestrator(
    ...
    pass_threshold=0.35,
    w_ix=0.10,         # ← orchestrator에서 w_ix 파라미터 제거 예정
)
```

**수정**: `w_ix=0.10` 제거. `scoring_weights=None`으로 두면 기본값 사용.

### 4-2. `orchestrator.py:139` — weights 미전달

```python
# 현재 (충돌)
p_score, l_score, _ = integrate_verification_v2(metrics, self._pass_threshold)

# 수정 후
p_score, l_score, _ = integrate_verification_v2(metrics, self._pass_threshold, self._weights)
```

### 4-3. `orchestrator.py:150` — total_score 하드코딩

```python
# 현재 (충돌)
total_score = avg_perception * 0.45 + avg_logical * 0.55

# 수정 후
w = self._weights
total_score = avg_perception * w.total_perception + avg_logical * w.total_logical
```

### 4-4. `orchestrator.py:153` — compute_scene_difficulty 시그니처 불일치

```python
# 현재 (충돌)
difficulty = compute_scene_difficulty(answer_obj_metrics, self._w_ix)

# 수정 후
difficulty = compute_scene_difficulty(answer_obj_metrics, self._weights)
```

### 4-5. `factory.py:109` — w_ix 전달

```python
# 현재 (충돌)
return ValidatorOrchestrator(
    ...
    w_ix=cfg.thresholds.w_ix,   # ← 제거 예정
)

# 수정 후
weights = ScoringWeights(**cfg.weights.model_dump())
return ValidatorOrchestrator(
    ...
    scoring_weights=weights,
)
```

### 4-6. `config/schema.py:101-108` — ValidatorThresholdsConfig.w_ix

```python
# 현재
class ValidatorThresholdsConfig(BaseModel):
    is_hidden_min_conditions: int = 2
    pass_threshold: float = 0.35
    w_ix: float = 0.10           # ← weights 로 이관 예정, 제거

    @field_validator("pass_threshold", "w_ix")   # ← w_ix 제거
    ...
```

**수정**: `w_ix` 필드와 해당 validator에서 `"w_ix"` 제거.

### 4-7. `conf/validator.yaml:17` — w_ix 항목

```yaml
# 현재 (충돌)
thresholds:
  is_hidden_min_conditions: 2
  pass_threshold: 0.35
  w_ix: 0.10              # ← 제거

# 수정 후: weights: 섹션으로 이동
weights:
  difficulty_interaction: 0.10
  ...
```

### 4-8. `tests/test_validator_scoring.py:191` — total_score 하드코딩

```python
# 현재 (충돌)
expected_total = p * 0.45 + l * 0.55

# 수정 후
from discoverex.domain.services.verification import ScoringWeights
w = ScoringWeights()
expected_total = p * w.total_perception + l * w.total_logical
```

### 4-9. `tests/test_validator_scoring.py:151-154` — 주석 (구 수식)

```python
# 현재 (주석만 충돌, 테스트 자체는 통과)
# sigma=1 → 0.20*(1/1) + 0.20*(1-0.0) = 0.40 (perception)
# hop=4/diameter=4, degree_norm=1.0 → 0.20*1.0 + 0.15*1.0 = 0.35 (logical)
# total = 0.40*0.45 + 0.35*0.55 = 0.3725 >= 0.35

# 수정 후
# perception = (0.5*(1/1) + 0.5*1.0) / 1.0 = 1.0
# logical    = (0.55*1.0 + 0.45*1.0) / 1.0 = 1.0
# total      = 1.0*0.45 + 1.0*0.55 = 1.0 >= 0.35
```

### 4-10. `tests/test_validator_pipeline_smoke.py:59` — total_score 상한

```python
# 현재
assert 0.0 <= bundle.final.total_score <= 2.0  # 주석: scores can exceed 1.0

# 정규화 후 max = 1.0 이므로 상한을 1.0 으로 수정
assert 0.0 <= bundle.final.total_score <= 1.0
```

### 충돌 요약표

| 파일 | 위치 | 충돌 내용 | 수정 방향 |
|------|------|-----------|-----------|
| `test_validator_pipeline_smoke.py` | L31 | `w_ix=0.10` 전달 | 파라미터 제거 |
| `test_validator_pipeline_smoke.py` | L59 | 상한 `<= 2.0` | `<= 1.0` 으로 수정 |
| `orchestrator.py` | L139 | weights 미전달 | weights 파라미터 추가 |
| `orchestrator.py` | L150 | `0.45/0.55` 하드코딩 | `w.total_perception/logical` 사용 |
| `orchestrator.py` | L153 | `self._w_ix` 전달 | `self._weights` 전달 |
| `factory.py` | L109 | `w_ix=...` 전달 | `scoring_weights=...` 로 교체 |
| `config/schema.py` | L101-108 | `w_ix` 필드 존재 | 필드 및 validator에서 제거 |
| `conf/validator.yaml` | L17 | `w_ix: 0.10` | `weights:` 섹션으로 이동 |
| `tests/test_validator_scoring.py` | L191 | `0.45/0.55` 하드코딩 | `ScoringWeights()` 참조로 교체 |
| `tests/test_validator_scoring.py` | L151-154 | 구 수식 주석 | 정규화 수식으로 업데이트 |

---

## 5. 변경 파일 전체 목록

### 수정

| 파일 | 주요 변경 내용 |
|------|--------------|
| `domain/services/verification.py` | `ScoringWeights` 추가, 3개 함수 시그니처 변경, 정규화 수식 적용 |
| `config/schema.py` | `ValidatorWeightsConfig` 추가, `ValidatorPipelineConfig`에 `weights` 필드 추가, `ValidatorThresholdsConfig.w_ix` 제거 |
| `config/__init__.py` | `ValidatorWeightsConfig` export 추가 |
| `application/use_cases/validator/orchestrator.py` | `w_ix` → `scoring_weights`, `_run_phase4` 내 하드코딩 제거 |
| `bootstrap/factory.py` | `ScoringWeights` 빌드 후 orchestrator에 주입, `weights_path` 로드 로직 추가 |
| `conf/validator.yaml` | `thresholds.w_ix` 제거, `weights:` 섹션 추가, `weights_path:` 항목 추가 (기본 null) |
| `adapters/inbound/cli/main.py` | `fit-weights` 커맨드 추가 |
| `tests/test_validator_scoring.py` | 주석 업데이트, `ScoringWeights` import, `expected_total` 수식 교체 |
| `tests/test_validator_pipeline_smoke.py` | `w_ix` 제거, 상한 1.0으로 수정 |

### 신규

| 파일 | 내용 |
|------|------|
| `domain/services/weight_fitter.py` | `WeightFitter` 클래스 (hinge loss + Nelder-Mead) |

### 변경 없음

| 파일 | 이유 |
|------|------|
| `domain/verification.py` | VerificationBundle/FinalVerification 구조 그대로 |
| `models/types.py` | ValidatorInput, PhysicalMetadata 등 그대로 |
| `adapters/outbound/models/*` | 포트 구현체 그대로 |
| `application/ports/models.py` | 포트 인터페이스 그대로 |
| `domain/services/judgement.py` | validator 미사용 |
