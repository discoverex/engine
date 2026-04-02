# Validator 파이프라인 구현 계획

> 기반 문서: `instruction_1.md`
> 작성일: 2026-03-03
> 목표: VRAM 8GB 최적화 4단계 연쇄 검증 파이프라인 구현

---

## 개요

`instruction_1.md`에 정의된 4단계 검증 파이프라인을 기존 Discoverex Engine의 Hexagonal Architecture에 통합 구현한다.
기존 `PerceptionPort`와 `VerificationBundle` 도메인 계약을 확장하여 MobileSAM → Moondream2 → YOLO+CLIP → CANON Assembler 순서로 실행되는 순차 파이프라인을 완성한다.

---

## 현재 아키텍처 연결점 분석

### Phase ↔ 기존 구조 대응표

| Validator Phase | 기존 구조 대응 | 처리 방식 |
|----------------|---------------|-----------|
| Phase 1 (MobileSAM) | `HiddenRegionPort` | 신규 포트 `PhysicalExtractionPort` 추가, 신규 어댑터 구현 |
| Phase 2 (Moondream2) | `PerceptionPort` (부분) | 신규 포트 `LogicalExtractionPort` 추가, 신규 어댑터 구현 |
| Phase 3 (YOLO+CLIP) | `PerceptionPort` | 신규 포트 `VisualVerificationPort` 추가, 병렬 어댑터 구현 |
| Phase 4 (CANON) | `services/verification.py` | 기존 파일에 함수 3종 추가 확장 |

### 기존 도메인 타입 재활용

| 기존 타입 | 재활용 방식 |
|----------|------------|
| `VerificationBundle` | 스키마 변경 없이 재사용 — `logical`·`perception`·`final` 구조 그대로 |
| `VerificationResult.signals` | `sigma_threshold`, `hop`, `degree_norm`, `DRR` 값을 딕셔너리로 저장 |
| `Region.Geometry` | `occlusion_ratio`, `z_index`, `z_depth_hop`, `neighbor_count` 필드 추가 |
| `Difficulty` | `score` 필드에 `Scene_Difficulty` 수식 결과 저장 |

---

## 파일 변경 로드맵

범례: `[NEW]` 신규 생성 · `[MOD]` 기존 파일 수정

```
engine/
│
├── src/discoverex/
│   │
│   ├── domain/
│   │   ├── region.py                              [MOD]  Geometry에 z_index, occlusion_ratio, z_depth_hop, neighbor_count 필드 추가
│   │   ├── verification.py                        [MOD]  VerificationResult.signals 표준 키 docstring 추가
│   │   └── services/
│   │       └── verification.py                    [MOD]  resolve_answer(), compute_difficulty(), compute_scene_difficulty(), integrate_verification_v2() 추가
│   │
│   ├── models/
│   │   └── types.py                               [MOD]  PhysicalMetadata, LogicalStructure, VisualVerification, ValidatorInput 데이터클래스 추가
│   │
│   ├── application/
│   │   ├── ports/
│   │   │   └── models.py                          [MOD]  PhysicalExtractionPort, LogicalExtractionPort, VisualVerificationPort Protocol 추가
│   │   └── use_cases/
│   │       └── validator/
│   │           ├── __init__.py                    [NEW]  패키지 초기화
│   │           └── orchestrator.py                [NEW]  ValidatorOrchestrator — 4단계 순차 실행 + VRAM 바톤 터치
│   │
│   ├── adapters/
│   │   ├── inbound/cli/
│   │   │   └── main.py                            [MOD]  `validate` CLI 명령어 추가
│   │   └── outbound/models/
│   │       ├── dummy.py                           [MOD]  DummyPhysicalExtraction, DummyLogicalExtraction, DummyVisualVerification 추가
│   │       ├── hf_mobilesam.py                    [NEW]  MobileSAMAdapter — Phase 1 물리 메타데이터 추출
│   │       ├── hf_moondream2.py                   [NEW]  Moondream2Adapter — Phase 2 논리 관계 추출 (4-bit 양자화)
│   │       └── hf_yolo_clip.py                    [NEW]  YoloCLIPAdapter — Phase 3 YOLO+CLIP 병렬 시각 검증
│   │
│   ├── bootstrap/
│   │   └── factory.py                             [MOD]  Validator용 포트 바인딩 추가 (build_validator_context)
│   │
│   └── config/
│       └── schema.py                              [MOD]  ValidatorModelsConfig, ValidatorThresholdsConfig Pydantic 모델 추가
│
├── conf/
│   ├── validator.yaml                             [NEW]  Validator 파이프라인 Hydra 진입점 설정
│   └── models/
│       ├── physical_extraction/
│       │   └── mobilesam.yaml                     [NEW]  MobileSAM 모델 설정
│       ├── logical_extraction/
│       │   └── moondream2.yaml                    [NEW]  Moondream2 4-bit 양자화 설정
│       └── visual_verification/
│           └── yolo_clip.yaml                     [NEW]  YOLOv10-N + CLIP 병렬 설정 (max 4GB)
│
└── tests/
    ├── test_validator_pipeline_smoke.py           [NEW]  Dummy 어댑터 기반 전체 파이프라인 E2E 테스트
    └── test_validator_scoring.py                  [NEW]  D(obj) 수식, is_hidden 판정, total_score 임계값 단위 테스트
```

### 변경 규모 요약

| 구분 | 수량 | 대상 |
|------|------|------|
| **신규 생성** | **9개** | `validator/orchestrator.py`, `hf_mobilesam.py`, `hf_moondream2.py`, `hf_yolo_clip.py`, `validator.yaml`, `mobilesam.yaml`, `moondream2.yaml`, `yolo_clip.yaml`, 테스트 2개 |
| **기존 수정** | **8개** | `region.py`, `verification.py`, `services/verification.py`, `types.py`, `ports/models.py`, `dummy.py`, `main.py`, `schema.py` + `factory.py` |
| **변경 없음** | — | `scene.py`, `goal.py`, `storage.py`, `tracking.py`, `delivery/`, `orchestrator/`, `infra/` 등 기존 파이프라인 전체 |

---

## 구현 계획

### 1단계: 도메인 모델 확장

**파일:** `src/discoverex/domain/region.py`

`Geometry` 클래스에 물리적 메타데이터 필드 추가:
```python
# 추가할 필드
z_index: int = 0                    # 레이어 Z-order
occlusion_ratio: float = 0.0        # 가림 비율 (0~1)
z_depth_hop: int = 0                # 레이어 깊이 (Shortest Path)
neighbor_count: int = 0             # 군집 반경 내 인접 객체 수
euclidean_distances: list[float] = []  # 다른 객체까지의 유클리드 거리
```

**파일:** `src/discoverex/domain/verification.py`

`VerificationResult.signals`에 표준 키 정의 추가 (docstring 수준):
```
signals 표준 키:
  perception: sigma_threshold, detail_retention_rate, occlusion_ratio
  logical:    hop, diameter, degree, degree_norm
  final:      is_hidden, difficulty_score, pass_reason
```

---

### 2단계: 모델 타입 정의

**파일:** `src/discoverex/models/types.py`

각 Phase 입출력 타입 추가:

```python
# Phase 1 출력
@dataclass
class PhysicalMetadata:
    regions: list[dict]          # bbox, center, area per object
    occlusion_map: dict          # {obj_id: occlusion_ratio}
    z_index_map: dict            # {obj_id: z_index}
    z_depth_hop_map: dict        # {obj_id: hop}
    cluster_density_map: dict    # {obj_id: neighbor_count}
    euclidean_distance_map: dict # {obj_id: [distances]}

# Phase 2 출력
@dataclass
class LogicalStructure:
    relations: list[dict]        # [{subject, predicate, object}]
    degree_map: dict             # {obj_id: degree}
    hop_map: dict                # {obj_id: hop from root}
    diameter: float              # 그래프 직경

# Phase 3 출력
@dataclass
class VisualVerification:
    sigma_threshold_map: dict    # {obj_id: sigma_threshold}
    detail_retention_rate_map: dict  # {obj_id: DRR}

# Phase 4 입력 집계
@dataclass
class ValidatorInput:
    physical: PhysicalMetadata
    logical: LogicalStructure
    visual: VisualVerification
```

---

### 3단계: 포트(인터페이스) 정의

**파일:** `src/discoverex/application/ports/models.py`

신규 포트 추가:

```python
class PhysicalExtractionPort(Protocol):
    """Phase 1: MobileSAM 기반 물리 메타데이터 추출 포트"""
    def load(self, handle: ModelHandle) -> None: ...
    def extract(self, composite_image: Path, object_layers: list[Path]) -> PhysicalMetadata: ...
    def unload(self) -> None: ...

class LogicalExtractionPort(Protocol):
    """Phase 2: Moondream2 기반 논리 관계 추출 포트"""
    def load(self, handle: ModelHandle) -> None: ...
    def extract(self, composite_image: Path, physical: PhysicalMetadata) -> LogicalStructure: ...
    def unload(self) -> None: ...

class VisualVerificationPort(Protocol):
    """Phase 3: YOLO+CLIP 병렬 시각 난이도 검증 포트"""
    def load(self, handle: ModelHandle) -> None: ...
    def verify(self, composite_image: Path, sigma_levels: list[float]) -> VisualVerification: ...
    def unload(self) -> None: ...
```

---

### 4단계: 어댑터 구현

**경로:** `src/discoverex/adapters/outbound/models/`

#### Phase 1 어댑터: `hf_mobilesam.py`

```
MobileSAMAdapter(PhysicalExtractionPort)
├── load(): MobileSAM 모델 로드 (VRAM)
├── extract():
│   ├── [Pre-processing] 레이어 vs composite 픽셀 비교 → z_index, occlusion_ratio, z_depth_hop
│   ├── MobileSAM segmentation → 정밀 Mask 생성
│   ├── Mask → bbox, center, area 산출
│   ├── 유클리드 거리 + 군집 밀집도 계산
│   └── 결과 병합 → PhysicalMetadata
└── unload(): del model + torch.cuda.empty_cache()
```

#### Phase 2 어댑터: `hf_moondream2.py`

```
Moondream2Adapter(LogicalExtractionPort)
├── load(): Moondream2 4-bit 양자화 로드 (VRAM)
├── extract():
│   ├── Context-Aware Prompt 구성 (Phase 1 좌표 주입)
│   ├── VLM 추론 → 관계 JSON 추출
│   └── NetworkX 그래프 연산 → degree, hop, diameter
└── unload(): del model + torch.cuda.empty_cache()
```

#### Phase 3 어댑터: `hf_yolo_clip.py`

```
YoloCLIPAdapter(VisualVerificationPort)
├── load(): YOLOv10-N + CLIP ViT-B/32 병렬 로드 (합계 4GB 미만)
├── verify():
│   ├── 블러 이미지 배치 생성 (σ = 1, 2, 4, 8, 16)
│   ├── [YOLO Branch] 객체별 소실 임계 블러레벨 (sigma_threshold) 추적
│   ├── [CLIP Branch] 원본 대비 코사인 유사도 → DRR 산출
│   └── 통합 → VisualVerification
└── unload(): del yolo_model, clip_model + torch.cuda.empty_cache()
```

---

### 5단계: 유스케이스 - Validator 오케스트레이터

**파일:** `src/discoverex/application/use_cases/validator/orchestrator.py`

```python
class ValidatorOrchestrator:
    """
    4단계 순차 실행 + VRAM 바톤 터치 전략
    각 Phase는 독립 함수로 격리, JSON 구조체로만 데이터 전달
    """

    def run(self, composite_image: Path, object_layers: list[Path]) -> VerificationBundle:
        # Phase 1: 물리 데이터 추출
        physical = self._run_phase1(composite_image, object_layers)

        # Phase 2: 논리 관계 추출 (Phase 1 좌표 주입)
        logical_struct = self._run_phase2(composite_image, physical)

        # Phase 3: 시각적 난이도 검증
        visual = self._run_phase3(composite_image)

        # Phase 4: 정답 판정 + CANON 조립 (순수 연산)
        return self._run_phase4(physical, logical_struct, visual)

    def _run_phase1(self, ...) -> PhysicalMetadata:
        self.physical_port.load(self.physical_handle)
        result = self.physical_port.extract(composite_image, object_layers)
        self.physical_port.unload()  # VRAM 초기화
        return result

    def _run_phase2(self, ...) -> LogicalStructure:
        self.logical_port.load(self.logical_handle)
        result = self.logical_port.extract(composite_image, physical)
        self.logical_port.unload()  # VRAM 초기화
        return result

    def _run_phase3(self, ...) -> VisualVerification:
        self.visual_port.load(self.visual_handle)
        result = self.visual_port.verify(composite_image, sigma_levels=[1, 2, 4, 8, 16])
        self.visual_port.unload()  # VRAM 종료
        return result

    def _run_phase4(self, ...) -> VerificationBundle:
        # Answer Resolver: 2개 이상 조건 충족 시 정답 오브젝트 확정
        # 난이도 산출: D(obj) 수식 적용
        # VerificationBundle 집계: perception × 0.45 + logical × 0.55
        ...
```

---

### 6단계: Phase 4 도메인 서비스 확장

**파일:** `src/discoverex/domain/services/verification.py`

#### 6-1. Answer Resolver (`is_hidden` 판정)

```python
def resolve_answer(obj_metrics: dict) -> bool:
    """
    조건 2개 이상 충족 시 정답 오브젝트로 판정
    """
    conditions = [
        obj_metrics["occlusion_ratio"] > 0.3,
        obj_metrics["sigma_threshold"] <= 4,
        obj_metrics["degree"] >= 3,
        obj_metrics["z_depth_hop"] >= 2,
        obj_metrics["neighbor_count"] >= 3,
    ]
    return sum(conditions) >= 2
```

#### 6-2. 난이도 산출 (`D(obj)` 수식)

```python
def compute_difficulty(obj_metrics: dict, w_ix: float = 0.10) -> float:
    """
    D(obj) = 0.25 · occlusion_ratio²
           + 0.20 · (1 / σ_threshold)
           + 0.20 · (hop / diameter)
           + 0.15 · degree_norm²
           + 0.20 · (1 - DRR)
           + w_ix · occlusion_ratio · (hop / diameter)
    """
    occlusion  = obj_metrics["occlusion_ratio"]
    sigma      = obj_metrics["sigma_threshold"]
    hop        = obj_metrics["hop"]
    diameter   = obj_metrics["diameter"]
    degree_n   = obj_metrics["degree_norm"]
    drr        = obj_metrics["detail_retention_rate"]

    return (
        0.25 * occlusion ** 2
        + 0.20 * (1 / sigma)
        + 0.20 * (hop / diameter)
        + 0.15 * degree_n ** 2
        + 0.20 * (1 - drr)
        + w_ix * occlusion * (hop / diameter)
    )

def compute_scene_difficulty(answer_objs: list[dict]) -> float:
    """
    Scene_Difficulty = (1 / |answer|) · Σ D(obj)
    """
    if not answer_objs:
        return 0.0
    return sum(compute_difficulty(obj) for obj in answer_objs) / len(answer_objs)
```

#### 6-3. VerificationBundle 집계

```python
def integrate_verification_v2(
    physical: PhysicalMetadata,
    logical_struct: LogicalStructure,
    visual: VisualVerification,
    obj_id: str,
) -> VerificationBundle:
    """
    perception = 0.20 · (1 / σ) + 0.20 · (1 - DRR)
    logical    = 0.20 · (hop / diameter) + 0.15 · degree_norm²
    total      = perception × 0.45 + logical × 0.55
    pass       = total_score >= 0.35
    """
    sigma   = visual.sigma_threshold_map[obj_id]
    drr     = visual.detail_retention_rate_map[obj_id]
    hop     = logical_struct.hop_map[obj_id]
    diam    = logical_struct.diameter
    deg_n   = logical_struct.degree_map[obj_id] / max_degree  # 정규화

    perception = 0.20 * (1 / sigma) + 0.20 * (1 - drr)
    logical    = 0.20 * (hop / diam) + 0.15 * deg_n ** 2
    total      = perception * 0.45 + logical * 0.55

    return VerificationBundle(
        logical=VerificationResult(score=logical, pass_=total >= 0.35, signals={...}),
        perception=VerificationResult(score=perception, pass_=total >= 0.35, signals={...}),
        final=FinalVerification(
            total_score=total,
            pass_=total >= 0.35,
            reason=None if total >= 0.35 else "difficulty_too_low",
        ),
    )
```

---

### 7단계: 설정 확장

#### 신규 Hydra 설정 파일

**`conf/models/physical_extraction/mobilesam.yaml`**
```yaml
_target_: discoverex.adapters.outbound.models.hf_mobilesam.MobileSAMAdapter
model_id: "ChaoningZhang/MobileSAM"
device: cuda
dtype: float16
```

**`conf/models/logical_extraction/moondream2.yaml`**
```yaml
_target_: discoverex.adapters.outbound.models.hf_moondream2.Moondream2Adapter
model_id: "vikhyat/moondream2"
quantization: 4bit
device: cuda
```

**`conf/models/visual_verification/yolo_clip.yaml`**
```yaml
_target_: discoverex.adapters.outbound.models.hf_yolo_clip.YoloCLIPAdapter
yolo_model_id: "THU-MIG/yolov10-n"
clip_model_id: "openai/clip-vit-base-patch32"
sigma_levels: [1, 2, 4, 8, 16]
device: cuda
max_vram_gb: 4.0
```

**`conf/validator.yaml`** (신규 파이프라인 진입점)
```yaml
defaults:
  - models/physical_extraction: mobilesam
  - models/logical_extraction: moondream2
  - models/visual_verification: yolo_clip
  - adapters/artifact_store: local
  - adapters/metadata_store: local_json
  - adapters/tracker: mlflow_local
  - runtime/model_runtime: gpu
  - runtime/env: default

thresholds:
  is_hidden_min_conditions: 2
  pass_threshold: 0.35
  w_ix: 0.10
```

#### `config/schema.py` 확장

```python
class ValidatorModelsConfig(BaseModel):
    physical_extraction: HydraComponentConfig
    logical_extraction: HydraComponentConfig
    visual_verification: HydraComponentConfig

class ValidatorThresholdsConfig(BaseModel):
    is_hidden_min_conditions: int = 2
    pass_threshold: float = 0.35
    w_ix: float = 0.10  # 교호작용 가중치 (초기값, 데이터 누적 후 조정)
```

---

### 8단계: CLI 통합

**파일:** `src/discoverex/adapters/inbound/cli/main.py`

신규 명령어 추가:
```python
@app.command("validate")
def validate_cmd(
    composite_image: Path = typer.Argument(...),
    object_layers: list[Path] = typer.Option(...),
    config_name: str = typer.Option("validator"),
) -> None:
    """
    4단계 Validator 파이프라인 실행
    출력: {"scene_id", "status", "verification_bundle", "scene_json"}
    """
```

---

## 구현 순서 (우선순위)

| 순서 | 작업 | 파일 |
|------|------|------|
| 1 | 도메인 모델 확장 (`Geometry` 필드 추가) | `domain/region.py` |
| 2 | 모델 타입 정의 추가 | `models/types.py` |
| 3 | 신규 포트 인터페이스 정의 | `application/ports/models.py` |
| 4 | Phase 4 도메인 서비스 구현 | `domain/services/verification.py` |
| 5 | Validator 오케스트레이터 스켈레톤 | `application/use_cases/validator/orchestrator.py` |
| 6 | Dummy 어댑터 구현 (테스트용) | `adapters/outbound/models/dummy.py` 확장 |
| 7 | 설정 스키마 및 Hydra YAML 추가 | `config/schema.py`, `conf/validator.yaml` |
| 8 | CLI 명령어 통합 | `adapters/inbound/cli/main.py` |
| 9 | MobileSAM 어댑터 구현 | `adapters/outbound/models/hf_mobilesam.py` |
| 10 | Moondream2 어댑터 구현 | `adapters/outbound/models/hf_moondream2.py` |
| 11 | YOLO+CLIP 병렬 어댑터 구현 | `adapters/outbound/models/hf_yolo_clip.py` |
| 12 | 통합 테스트 작성 | `tests/test_validator_pipeline_smoke.py` |

---

## 주요 설계 결정

### VRAM 관리 전략
- 각 Phase를 독립 함수로 격리: `load() → extract() → unload()` 패턴
- `unload()`는 항상 `del model + torch.cuda.empty_cache()` 순서로 호출
- Phase 3만 예외: YOLO + CLIP 동시 로드하되 합계 4GB 미만 유지

### 데이터 전달 방식
- Phase 간 데이터는 순수 Python 데이터클래스(JSON 직렬화 가능)로만 전달
- VRAM 텐서를 Phase 간에 공유하지 않음 (메모리 바톤 터치 원칙)
- Phase 2는 Phase 1의 좌표를 프롬프트로 주입 (Context-Aware Prompting)

### 기존 계약 준수
- `VerificationBundle` 스키마 변경 없이 재사용 (신호값을 `signals` 딕셔너리에 저장)
- `Difficulty` 도메인 타입에 `score` 필드로 `Scene_Difficulty` 값 저장
- Hexagonal 경계 규칙 준수: 오케스트레이터는 포트만 의존

### 임계값 조정 계획
- `w_ix` (교호작용 가중치): 초기값 0.10, 씬 100개 이상 생성 후 분포 기반 조정
- `pass_threshold` (0.35): 데이터 누적 후 보정 필요
- `is_hidden_min_conditions` (2개): 초기 운영 후 false positive/negative 분석 후 조정

---

## 테스트 전략

### Dummy 어댑터 활용 (VRAM 없이 테스트)
```python
# tests/test_validator_pipeline_smoke.py
def test_validator_orchestrator_dummy():
    """Dummy 어댑터로 전체 4단계 파이프라인 실행 검증"""
    orchestrator = ValidatorOrchestrator(
        physical_port=DummyPhysicalExtraction(),
        logical_port=DummyLogicalExtraction(),
        visual_port=DummyVisualVerification(),
    )
    bundle = orchestrator.run(composite_image=..., object_layers=[...])
    assert bundle.final.pass_ is True or False  # 결과 구조 검증
    assert 0.0 <= bundle.final.total_score <= 1.0
```

### 수식 단위 테스트
```python
# tests/test_validator_scoring.py
def test_compute_difficulty_formula():
    """D(obj) 수식의 경계값 및 정상 동작 검증"""

def test_integrate_verification_thresholds():
    """total_score >= 0.35 조건 검증"""

def test_answer_resolver_conditions():
    """is_hidden 판정 조건 2개 이상 충족 로직 검증"""
```
